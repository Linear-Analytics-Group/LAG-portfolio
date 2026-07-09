"""Entrypoint and orchestrator for the ERP-to-Dataverse inventory sync.

Reads the mock ERP inventory feed from ``data/erp_mock_inventory_data_feed.csv``,
collapses duplicate SKU rows to their last-seen value, and idempotently PATCHes
each resulting record into Dataverse via ``lagsol_inventoryitems`` using its
``lagsol_skuid`` alternate key.

Every piece of this module besides :func:`sync_inventory_records` is generic
scaffolding supplied by ``lag_service_kit`` (configuration, logging, record
reading, dedup) and ``lag_data_utils`` (the Dataverse transport client).
``sync_inventory_records`` is the one function specific to this service —
it is the only place that knows what an inventory record looks like.

Environment
-----------
AZURE_TENANT_ID : str
    Microsoft Entra ID tenant GUID for the target Dataverse environment.
AZURE_CLIENT_ID : str
    Application (client) ID of the registered Entra ID app.
AZURE_CLIENT_SECRET : str
    Client secret credential for the registered Entra ID application.
DATAVERSE_URL : str
    Root URL of the target Dataverse environment
    (e.g., ``"https://org.crm.dynamics.com"``).
LOG_LEVEL : str
    Root logging level for the structured logging matrix. Optional,
    defaults to ``"INFO"``.

All variables are read via the :class:`config.InventorySyncSettings` schema,
which sources process environment variables first and falls back to the
``.env`` file at the repository root.
"""

import logging
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import requests
from pydantic import ValidationError

from config import InventorySyncSettings
from lag_data_utils.clients.dataverse import DataverseAuthenticationError, DataverseClient
from lag_service_kit.dedupe import dedupe_last_seen
from lag_service_kit.logging import configure_logging
from lag_service_kit.readers import CsvRecordReader

logger: logging.Logger = logging.getLogger(__name__)

CSV_PATH: Path = Path(__file__).parent / "data" / "erp_mock_inventory_data_feed.csv"
ENTITY_SET: str = "lagsol_inventoryitems"
ALTERNATE_KEY_FIELD: str = "lagsol_skuid"
DEDUPE_KEY: str = "sku_id"


def sync_inventory_records(client: DataverseClient, records: pd.DataFrame) -> Dict[str, int]:
    """Upsert each inventory record into Dataverse via idempotent PATCH.

    Parameters
    ----------
    client : DataverseClient
        An authenticated Dataverse client.
    records : pd.DataFrame
        Deduplicated inventory records, with ``sku_id``, ``item_name``, and
        ``unit_price`` columns.

    Returns
    -------
    Dict[str, int]
        Counts under the keys ``created``, ``updated``, and ``failed``,
        classified from each record's HTTP response status code
        (201 Created, 204 No Content) or a raised ``requests.HTTPError``.
    """
    result: Dict[str, int] = {"created": 0, "updated": 0, "failed": 0}

    for row in records.itertuples(index=False):
        payload: Dict[str, Any] = {
            "lagsol_name": row.item_name,
            "lagsol_unitprice": row.unit_price,
        }
        try:
            response = client.upsert_record(
                entity_set=ENTITY_SET,
                alternate_key_name=ALTERNATE_KEY_FIELD,
                key_value=row.sku_id,
                payload=payload,
            )
        except requests.HTTPError as exc:
            logger.error("FAILED sku_id=%s: %s", row.sku_id, exc)
            result["failed"] += 1
            continue

        if response.status_code == 201:
            result["created"] += 1
        else:
            result["updated"] += 1

    return result


def main() -> int:
    """Run the full ERP-to-Dataverse inventory sync.

    Returns
    -------
    int
        Process exit code: ``0`` if every record synced without error,
        ``1`` if configuration was invalid, Entra ID authentication failed,
        or any record failed to sync.
    """
    configure_logging()

    try:
        settings = InventorySyncSettings()  # type: ignore[call-arg]  # fields sourced from env/`.env`
    except ValidationError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    configure_logging(settings.log_level)

    client = DataverseClient.from_settings(settings)
    try:
        client.acquire_bearer_token()
    except DataverseAuthenticationError as exc:
        logger.error("Authentication error: %s", exc)
        return 1

    records = dedupe_last_seen(CsvRecordReader().load(CSV_PATH), key=DEDUPE_KEY)
    result = sync_inventory_records(client, records)

    logger.info(
        "Sync complete: %d created, %d updated, %d failed (of %d records).",
        result["created"],
        result["updated"],
        result["failed"],
        len(records),
    )
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
