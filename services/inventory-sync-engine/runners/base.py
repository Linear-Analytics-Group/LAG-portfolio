"""Inventory-domain sync orchestration, destination-agnostic.

Fixes what an inventory record *is* — a deduplicated ``sku_id``,
``item_name``, ``unit_price`` row read from a CSV feed — and how it is
written to any OData v4 destination (an idempotent alternate-key upsert),
without assuming which destination that is. Solution-specific subclasses
(e.g. ``DataverseInventorySyncRunner``) supply only their own settings,
client construction, and field-name mapping.
"""

import logging
from abc import abstractmethod
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import requests

from lag_data_utils.clients.odata import ODataClient
from lag_service_kit.dedupe import dedupe_last_seen
from lag_service_kit.readers import CsvRecordReader
from lag_service_kit.runners import BaseSyncRunner

logger: logging.Logger = logging.getLogger(__name__)

CSV_PATH: Path = Path(__file__).parent.parent / "data" / "erp_mock_inventory_data_feed.csv"
DEDUPE_KEY: str = "sku_id"


class BaseInventorySyncRunner(BaseSyncRunner):
    """Destination-agnostic orchestration for the ERP inventory sync.

    Sits between ``lag_service_kit.runners.base.BaseSyncRunner`` (which
    knows nothing about inventory or Dataverse) and a destination-specific
    leaf class (which knows nothing about CSV reading or deduplication).
    This mirrors ``lag_data_utils.clients.odata.ODataClient``'s position
    between ``BaseClient`` and ``DataverseClient``: it implements the parts
    of the algorithm that are generic across every destination this
    service will ever support, and leaves the destination-specific parts
    as abstract hooks.

    Notes
    -----
    Subclasses must supply :attr:`entity_set`, :attr:`alternate_key_field`,
    and :meth:`build_payload`, plus :meth:`~BaseSyncRunner.load_settings`
    and :meth:`~BaseSyncRunner.build_client` inherited from
    ``BaseSyncRunner``. :meth:`load_records` and :meth:`sync_records` are
    implemented here and should not need to be overridden.
    """

    csv_path: Path = CSV_PATH
    dedupe_key: str = DEDUPE_KEY

    @property
    @abstractmethod
    def entity_set(self) -> str:
        """Pluralized logical name of the destination's inventory entity collection."""
        ...

    @property
    @abstractmethod
    def alternate_key_field(self) -> str:
        """Schema name of the destination field holding the SKU alternate key."""
        ...

    @abstractmethod
    def build_payload(self, row: Any) -> Dict[str, Any]:
        """Map one deduplicated inventory row to the destination's own field names.

        Parameters
        ----------
        row : Any
            A ``NamedTuple`` row from :meth:`load_records`, with ``sku_id``,
            ``item_name``, and ``unit_price`` attributes.

        Returns
        -------
        Dict[str, Any]
            Field-value pairs keyed by the destination's schema names,
            ready to pass as the ``payload`` argument to
            :meth:`~lag_data_utils.clients.odata.ODataClient.upsert_record`.
        """
        ...

    def load_records(self) -> pd.DataFrame:
        """Read the ERP CSV feed and collapse duplicate SKU rows.

        Returns
        -------
        pd.DataFrame
            Deduplicated inventory records, with ``sku_id``, ``item_name``,
            and ``unit_price`` columns.
        """
        return dedupe_last_seen(CsvRecordReader().load(self.csv_path), key=self.dedupe_key)

    def sync_records(self, client: ODataClient, records: pd.DataFrame) -> Dict[str, int]:
        """Upsert each inventory record into the destination via idempotent PATCH.

        Parameters
        ----------
        client : ODataClient
            An authenticated OData v4 client for the target destination.
        records : pd.DataFrame
            Deduplicated inventory records, as returned by
            :meth:`load_records`.

        Returns
        -------
        Dict[str, int]
            Counts under the keys ``created``, ``updated``, and ``failed``,
            classified from each record's HTTP response status code
            (201 Created, 204 No Content) or a raised ``requests.HTTPError``.
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
            except requests.HTTPError as exc:
                logger.error("FAILED %s=%s: %s", self.dedupe_key, key_value, exc)
                result["failed"] += 1
                continue

            if response.status_code == 201:
                result["created"] += 1
            else:
                result["updated"] += 1

        return result
