"""OData v4 write-protocol base, for any OData v4 destination.

Fixes how a deduplicated row is written to *any* OData v4 destination
— an idempotent alternate-key upsert — without assuming which
destination that is, which domain the record belongs to, or which
source produced the row. A future non-OData protocol (e.g. a
``runners/soap.py`` for a SOAP-based destination) implements this same
shape against its own ``ClientT``, with its own hooks and write loop,
so protocols never share write-loop code that doesn't actually apply
to both of them.
"""

import logging
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd
import requests
from lag_data_utils.clients.odata import ODataClient
from lag_service_kit.circuit_breaker import ConsecutiveFailureCircuitBreaker
from lag_service_kit.runners.base import BaseSyncRunner

logger: logging.Logger = logging.getLogger(__name__)


class BaseODataSyncRunner(BaseSyncRunner[ODataClient]):
    """OData v4 write-protocol orchestration for any destination/domain.

    Sits between ``lag_service_kit.runners.base.BaseSyncRunner`` (which
    knows nothing about OData or any particular domain) and a
    destination-specific leaf class (which knows nothing about the
    OData upsert mechanics). This mirrors
    ``lag_data_utils.clients.odata.ODataClient``'s position between
    ``BaseClient`` and ``DataverseClient``: it implements the parts of
    the write loop that are generic across every OData v4 destination,
    and leaves the destination-specific field mapping as abstract
    hooks. Knows nothing about source feeds or dedup — a destination
    leaf class combines this with a service's own domain mixin (e.g.
    ``InventoryDomainMixin``) to get both.

    Notes
    -----
    Subclasses must supply :attr:`entity_set`, :attr:`alternate_key_field`,
    and :meth:`build_payload`, plus :meth:`~BaseSyncRunner.load_settings`
    and :meth:`~BaseSyncRunner.build_client` inherited from
    ``BaseSyncRunner``. :meth:`sync_records` is implemented here and
    should not need to be overridden.

    :attr:`dedupe_key` is declared, not defined, here: it names the
    column :meth:`sync_records` reads each record's business key from,
    but *which* column that is is domain knowledge, not OData knowledge.
    A destination leaf class supplies it by also inheriting a domain
    mixin (e.g. ``InventoryDomainMixin``), which is the single place
    that value is ever set.
    """

    dedupe_key: str

    def __init__(
        self,
        max_workers: int,
        failure_threshold: int,
        **kwargs: Any,
    ) -> None:
        """Set this run's upsert concurrency and failure tolerance.

        Parameters
        ----------
        max_workers : int
            Worker threads used to upsert records concurrently in
            :meth:`sync_records`. No default here: a sensible number
            is a property of the calling service's own operational
            tuning (see e.g. ``defaults.DEFAULT_MAX_WORKERS`` in
            ``services/inventory-sync-engine``), not of this class.
        failure_threshold : int
            Consecutive failures (see
            ``lag_service_kit.circuit_breaker.ConsecutiveFailureCircuitBreaker``
            above) that trip :meth:`sync_records`'s circuit breaker,
            skipping every record not yet attempted. No default here,
            for the same reason as ``max_workers`` — mirroring
            ``ConsecutiveFailureCircuitBreaker.__init__``,
            ``CsvRecordReader.load_chunks``, and
            ``dedupe_last_seen_chunks``, none of which bake in a
            default for a value that's genuinely a service's own
            operational tuning decision.
        **kwargs : Any
            Forwarded, unexamined, to ``super().__init__()``.

        Returns
        -------
        None

        Notes
        -----
        This is the last class in the domain/protocol mixin chain with
        constructor parameters of its own — ``BaseSyncRunner`` defines
        none — so nothing further needs ``**kwargs`` forwarded to it.
        Still calls ``super().__init__()`` (with no arguments) rather
        than skip it, for the same cooperative-multiple-inheritance
        reason a domain mixin's ``__init__`` does.
        """
        super().__init__()
        self._max_workers = max_workers
        self._failure_threshold = failure_threshold

    @property
    @abstractmethod
    def entity_set(self) -> str:
        """Pluralized name of the destination's entity collection."""
        ...

    @property
    @abstractmethod
    def alternate_key_field(self) -> str:
        """Schema name of the destination's alternate-key field."""
        ...

    @abstractmethod
    def build_payload(self, row: Any) -> dict[str, Any]:
        """Map one deduplicated row to the destination's own field names.

        Parameters
        ----------
        row : Any
            A ``NamedTuple`` row from ``load_records()``, with
            whatever attributes the calling domain mixin's business
            schema defines.

        Returns
        -------
        dict[str, Any]
            Field-value pairs keyed by the destination's schema names,
            ready to pass as the ``payload`` argument to
            :meth:`~lag_data_utils.clients.odata.ODataClient.upsert_record`.
        """
        ...

    def _upsert_one(
        self,
        client: ODataClient,
        row: Any,
        breaker: ConsecutiveFailureCircuitBreaker,
    ) -> str:
        """Upsert a single record, classifying the outcome as a string.

        Parameters
        ----------
        client : ODataClient
            An authenticated OData v4 client for the target destination.
        row : Any
            A single ``NamedTuple`` row from :meth:`sync_records`'s
            ``records``.
        breaker : ConsecutiveFailureCircuitBreaker
            This run's shared circuit breaker (see :meth:`sync_records`).

        Returns
        -------
        str
            ``"created"``, ``"updated"``, ``"failed"``, or ``"skipped"``
            if ``breaker`` was already tripped when this call started.

        Notes
        -----
        Runs inside a worker thread (see :meth:`sync_records`) and
        deliberately returns a plain value rather than mutating any
        shared state — the caller aggregates results back on the main
        thread, so no lock is needed here and one record's failure can
        never corrupt another's count. ``breaker`` is the one piece of
        state genuinely shared across worker threads, and it is
        internally thread-safe for exactly this reason.

        Checks ``breaker.is_tripped`` before issuing any request at
        all: once tripped, every record not yet started is skipped
        without ever touching the network, rather than continuing to
        batter an already-failing destination for the rest of the run.

        Catches exactly ``requests.HTTPError`` (a rejected response),
        ``requests.ConnectionError`` (the connection itself failed), and
        ``requests.Timeout`` (no response within the configured timeout)
        — the categories of a genuinely retriable, per-record transport
        failure. Any other exception (e.g., a malformed URL from a code
        defect) is treated as a bug, not a sync failure, and propagates
        uncaught rather than being silently absorbed into ``failed`` for
        every remaining record.
        """
        if breaker.is_tripped:
            return "skipped"

        key_value = getattr(row, self.dedupe_key)
        try:
            response = client.upsert_record(
                entity_set=self.entity_set,
                alternate_key_name=self.alternate_key_field,
                key_value=key_value,
                payload=self.build_payload(row),
            )
        except (
            requests.HTTPError,
            requests.ConnectionError,
            requests.Timeout,
        ) as exc:
            logger.error(
                "FAILED %s=%s: %s: %s",
                self.dedupe_key,
                key_value,
                type(exc).__name__,
                exc,
                extra={
                    self.dedupe_key: key_value,
                    "exception_type": type(exc).__name__,
                },
            )
            if breaker.record_failure():
                logger.error(
                    "Circuit breaker tripped after %d consecutive "
                    "failures; skipping remaining records.",
                    self._failure_threshold,
                    extra={"failure_threshold": self._failure_threshold},
                )
            return "failed"

        breaker.record_success()
        return "created" if response.status_code == 201 else "updated"

    def sync_records(
        self, client: ODataClient, records: pd.DataFrame
    ) -> dict[str, int]:
        """Upsert every record concurrently via an idempotent PATCH.

        Parameters
        ----------
        client : ODataClient
            An authenticated OData v4 client for the target destination.
        records : pd.DataFrame
            Deduplicated records, as returned by a domain mixin's
            ``load_records()``.

        Returns
        -------
        dict[str, int]
            Counts under the keys ``created``, ``updated``, ``failed``,
            and ``skipped`` — the last being records never attempted
            because the circuit breaker had already tripped.

        Notes
        -----
        Dispatches up to :attr:`_max_workers` upserts at once via
        ``concurrent.futures.ThreadPoolExecutor``. This is an I/O-bound
        workload — each upsert spends almost all its time waiting on
        the network, not computing — so threads give real parallelism
        despite the GIL, without the much larger rewrite an async HTTP
        stack would require. Each worker classifies its own outcome
        (see :meth:`_upsert_one`) and returns a plain string; only the
        main thread ever increments ``result``, so no lock is needed
        and the per-record failure isolation this class has always
        guaranteed holds unchanged under concurrency.

        Builds a fresh
        ``lag_service_kit.circuit_breaker.ConsecutiveFailureCircuitBreaker``
        local to this call rather than storing one on ``self``, so a
        run's failure streak never leaks into a later, separate run on
        the same instance. Every future is still submitted up front —
        only futures the executor hasn't started running yet actually
        benefit from skipping (see :meth:`_upsert_one`); a batch no
        larger than :attr:`_max_workers` will already be fully in
        flight by the time the breaker could trip.
        """
        result: dict[str, int] = {
            "created": 0,
            "updated": 0,
            "failed": 0,
            "skipped": 0,
        }
        breaker = ConsecutiveFailureCircuitBreaker(self._failure_threshold)

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = [
                executor.submit(self._upsert_one, client, row, breaker)
                for row in records.itertuples(index=False)
            ]
            for future in as_completed(futures):
                result[future.result()] += 1

        return result
