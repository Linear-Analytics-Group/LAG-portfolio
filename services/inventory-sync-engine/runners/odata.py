"""OData v4 write-protocol base for inventory sync runners.

Fixes how a deduplicated inventory row is written to *any* OData v4
destination — an idempotent alternate-key upsert — without assuming
which destination that is or which source produced the row. Sibling
modules for a future non-OData protocol (e.g. ``runners/soap.py`` for a
SOAP-based destination) implement this same shape against their own
``ClientT``, with their own hooks and write loop, so protocols never
share write-loop code that doesn't actually apply to both of them.
"""

import logging
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict

import pandas as pd
import requests
from lag_data_utils.clients.odata import ODataClient
from lag_service_kit.runners import BaseSyncRunner

from defaults import DEFAULT_MAX_WORKERS

logger: logging.Logger = logging.getLogger(__name__)


class BaseODataInventorySyncRunner(BaseSyncRunner[ODataClient]):
    """OData v4 write-protocol orchestration for the ERP inventory sync.

    Sits between ``lag_service_kit.runners.base.BaseSyncRunner`` (which
    knows nothing about OData or inventory) and a destination-specific
    leaf class (which knows nothing about the OData upsert mechanics).
    This mirrors ``lag_data_utils.clients.odata.ODataClient``'s position
    between ``BaseClient`` and ``DataverseClient``: it implements the
    parts of the write loop that are generic across every OData v4
    destination, and leaves the destination-specific field mapping as
    abstract hooks. Knows nothing about source feeds or dedup — a
    destination leaf class combines this with
    ``runners.base.InventoryDomainMixin`` to get both.

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
    mixin (e.g. ``runners.base.InventoryDomainMixin``), which is the
    single place that value is ever set.
    """

    dedupe_key: str

    def __init__(
        self, max_workers: int = DEFAULT_MAX_WORKERS, **kwargs: Any
    ) -> None:
        """Set this run's upsert concurrency.

        Parameters
        ----------
        max_workers : int
            Worker threads used to upsert records concurrently in
            :meth:`sync_records`. Defaults to :data:`DEFAULT_MAX_WORKERS`.
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
        reason ``InventoryDomainMixin.__init__`` does.
        """
        super().__init__()
        self._max_workers = max_workers

    @property
    @abstractmethod
    def entity_set(self) -> str:
        """Pluralized name of the destination's inventory entity collection."""
        ...

    @property
    @abstractmethod
    def alternate_key_field(self) -> str:
        """Schema name of the destination's SKU alternate-key field."""
        ...

    @abstractmethod
    def build_payload(self, row: Any) -> Dict[str, Any]:
        """Map one deduplicated row to the destination's own field names.

        Parameters
        ----------
        row : Any
            A ``NamedTuple`` row from ``load_records()``, with ``sku_id``,
            ``item_name``, and ``unit_price`` attributes.

        Returns
        -------
        Dict[str, Any]
            Field-value pairs keyed by the destination's schema names,
            ready to pass as the ``payload`` argument to
            :meth:`~lag_data_utils.clients.odata.ODataClient.upsert_record`.
        """
        ...

    def _upsert_one(self, client: ODataClient, row: Any) -> str:
        """Upsert a single record, classifying the outcome as a string.

        Parameters
        ----------
        client : ODataClient
            An authenticated OData v4 client for the target destination.
        row : Any
            A single ``NamedTuple`` row from :meth:`sync_records`'s
            ``records``.

        Returns
        -------
        str
            ``"created"``, ``"updated"``, or ``"failed"``.

        Notes
        -----
        Runs inside a worker thread (see :meth:`sync_records`) and
        deliberately returns a plain value rather than mutating any
        shared state — the caller aggregates results back on the main
        thread, so no lock is needed here and one record's failure can
        never corrupt another's count.

        Catches exactly ``requests.HTTPError`` (a rejected response),
        ``requests.ConnectionError`` (the connection itself failed), and
        ``requests.Timeout`` (no response within the configured timeout)
        — the categories of a genuinely retriable, per-record transport
        failure. Any other exception (e.g., a malformed URL from a code
        defect) is treated as a bug, not a sync failure, and propagates
        uncaught rather than being silently absorbed into ``failed`` for
        every remaining record.
        """
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
            )
            return "failed"

        return "created" if response.status_code == 201 else "updated"

    def sync_records(
        self, client: ODataClient, records: pd.DataFrame
    ) -> Dict[str, int]:
        """Upsert every record concurrently via an idempotent PATCH.

        Parameters
        ----------
        client : ODataClient
            An authenticated OData v4 client for the target destination.
        records : pd.DataFrame
            Deduplicated inventory records, as returned by a
            source/domain layer's ``load_records()``.

        Returns
        -------
        Dict[str, int]
            Counts under the keys ``created``, ``updated``, and ``failed``.

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
        """
        result: Dict[str, int] = {"created": 0, "updated": 0, "failed": 0}

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = [
                executor.submit(self._upsert_one, client, row)
                for row in records.itertuples(index=False)
            ]
            for future in as_completed(futures):
                result[future.result()] += 1

        return result
