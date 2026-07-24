"""Connectivity smoke test against a real Dataverse environment.

The real-environment counterpart to ``run_mock_sync.py``: where that
script proves the engine runs with zero setup, this one proves a
specific Entra ID app registration and Dataverse environment are
correctly configured, before relying on the full sync engine against
them. Requires a filled-in ``.env`` (see ``.env.example``) and network
access to Microsoft Entra ID and the target Dataverse environment —
run ``run_mock_sync.py`` instead for a demo needing neither.

Uses the exact same ``InventorySyncSettings``/``DataverseClient``
wiring the real service uses, rather than a hand-rolled MSAL/requests
call, so success here means the sync engine's own auth and connection
path works too.

Run with::

    python3 test_connection.py
"""

import logging

import requests
from config import InventorySyncSettings
from lag_data_utils.clients.base import AuthenticationError
from lag_data_utils.clients.dataverse import DataverseClient
from lag_service_kit.logging import configure_logging
from pydantic import ValidationError

logger = logging.getLogger(__name__)


def main() -> int:
    """Authenticate and issue one read-only request against Dataverse.

    Returns
    -------
    int
        Process exit code: ``0`` if authentication succeeded and the
        Dataverse Web API responded, ``1`` if configuration was
        invalid, Entra ID authentication failed, or the Dataverse Web
        API request failed.
    """
    configure_logging("INFO")

    try:
        settings = InventorySyncSettings()
        client = DataverseClient.from_settings(settings)
        client.acquire_bearer_token()
        logger.info("Bearer token acquired — Entra ID auth succeeded.")

        entities = client.query_records(
            entity_set="EntityDefinitions",
            select_fields=["LogicalName"],
            top=5,
        )
    except ValidationError as exc:
        logger.error("Configuration error: %s", exc)
        return 1
    except AuthenticationError as exc:
        logger.error("Authentication error: %s", exc)
        return 1
    except requests.RequestException as exc:
        logger.error("Dataverse Web API request failed: %s", exc)
        return 1

    logger.info("Dataverse reachable — sample entities: %s", entities)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
