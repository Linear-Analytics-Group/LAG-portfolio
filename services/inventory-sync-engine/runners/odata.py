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
from typing import Any, Dict

import pandas as pd
import requests
from lag_data_utils.clients.odata import ODataClient
from lag_service_kit.runners import BaseSyncRunner

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

    def sync_records(
        self, client: ODataClient, records: pd.DataFrame
    ) -> Dict[str, int]:
        """Upsert each record into the destination via an idempotent PATCH.

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
            Counts under the keys ``created``, ``updated``, and ``failed``,
            classified from each record's HTTP response status code
            (201 Created, 204 No Content) or one of the exceptions listed
            below.

        Notes
        -----
        Catches exactly ``requests.HTTPError`` (a rejected response),
        ``requests.ConnectionError`` (the connection itself failed), and
        ``requests.Timeout`` (no response within the configured timeout)
        — the categories of a genuinely retriable, per-record transport
        failure. Any other exception (e.g., a malformed URL from a code
        defect) is treated as a bug, not a sync failure, and propagates
        uncaught rather than being silently absorbed into ``failed`` for
        every remaining record.
        """
        result: Dict[str, int] = {"created": 0, "updated": 0, "failed": 0}

        for row in records.itertuples(index=False):
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
                result["failed"] += 1
                continue

            if response.status_code == 201:
                result["created"] += 1
            else:
                result["updated"] += 1

        return result
