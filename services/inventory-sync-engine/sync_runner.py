"""Entrypoint and orchestrator for the ERP-to-Dataverse inventory sync.

Reads the mock ERP inventory feed from ``data/erp_mock_inventory_data_feed.csv``,
collapses duplicate SKU rows to their last-seen value, and idempotently PATCHes
each resulting record into Dataverse via ``lagsol_inventoryitems`` using its
``lagsol_skuid`` alternate key.

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

All four variables are read from a ``.env`` file at the repository root via
``python-dotenv``.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import requests
from dotenv import load_dotenv

from lag_data_utils.clients.dataverse import DataverseAuthenticationError, DataverseClient

CSV_PATH = Path(__file__).parent / "data" / "erp_mock_inventory_data_feed.csv"
ENTITY_SET = "lagsol_inventoryitems"
ALTERNATE_KEY_FIELD = "lagsol_skuid"


def load_erp_inventory_feed(csv_path: Path) -> pd.DataFrame:
    """Load and deduplicate the mock ERP inventory feed.

    Parameters
    ----------
    csv_path : Path
        Path to the ERP feed CSV. Expected columns are ``sku_id``,
        ``item_name``, and ``unit_price``.

    Returns
    -------
    pd.DataFrame
        One row per unique ``sku_id``. When a SKU appears more than once,
        the last row for that SKU in file order is kept, treating the feed
        as an append-only stream where later rows supersede earlier ones.

    Raises
    ------
    FileNotFoundError
        If ``csv_path`` does not exist.
    """
    feed = pd.read_csv(csv_path)
    return feed.drop_duplicates(subset="sku_id", keep="last")


def build_dataverse_client() -> DataverseClient:
    """Construct a ``DataverseClient`` from environment configuration.

    Returns
    -------
    DataverseClient
        A client authenticated against the Dataverse environment identified
        by ``DATAVERSE_URL``.

    Raises
    ------
    RuntimeError
        If any of ``AZURE_TENANT_ID``, ``AZURE_CLIENT_ID``,
        ``AZURE_CLIENT_SECRET``, or ``DATAVERSE_URL`` is unset or empty.
    """
    required_vars = (
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "DATAVERSE_URL",
    )
    values = {name: os.getenv(name, "").strip() for name in required_vars}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required environment variable(s): {', '.join(missing)}")

    return DataverseClient(
        tenant_id=values["AZURE_TENANT_ID"],
        client_id=values["AZURE_CLIENT_ID"],
        client_secret=values["AZURE_CLIENT_SECRET"],
        environment_url=values["DATAVERSE_URL"],
    )


def sync_inventory_records(client: DataverseClient, records: pd.DataFrame) -> Dict[str, int]:
    """Upsert each inventory record into Dataverse via idempotent PATCH.

    Parameters
    ----------
    client : DataverseClient
        An authenticated Dataverse client.
    records : pd.DataFrame
        Deduplicated inventory records, as returned by
        ``load_erp_inventory_feed``.

    Returns
    -------
    Dict[str, int]
        Counts under the keys ``created``, ``updated``, and ``failed``,
        classified from each record's HTTP response status code
        (201 Created, 204 No Content) or a raised ``requests.HTTPError``.
    """
    result = {"created": 0, "updated": 0, "failed": 0}

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
            print(f"FAILED sku_id={row.sku_id}: {exc}", file=sys.stderr)
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
        ``1`` if any record failed or configuration was invalid.
    """
    load_dotenv()

    try:
        client = build_dataverse_client()
    except (RuntimeError, DataverseAuthenticationError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    records = load_erp_inventory_feed(CSV_PATH)
    result = sync_inventory_records(client, records)

    print(
        f"Sync complete: {result['created']} created, "
        f"{result['updated']} updated, {result['failed']} failed "
        f"(of {len(records)} records)."
    )
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())