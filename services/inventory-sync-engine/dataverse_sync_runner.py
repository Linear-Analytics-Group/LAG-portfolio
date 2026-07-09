"""Entrypoint for the ERP-to-Dataverse inventory sync.

Wires together five collaborators and owns none of their logic itself:

- ``lag_service_kit.runners.base.BaseSyncRunner`` — the source-,
  destination-, and domain-agnostic sync algorithm (settings, logging,
  auth, read, write, report), generic over the transport client type.
- ``runners.base.InventoryDomainMixin`` — source-agnostic,
  protocol-agnostic inventory domain logic (SKU dedup, binding to a
  composed source).
- ``runners.odata.BaseODataInventorySyncRunner`` — domain-agnostic OData
  v4 write-protocol logic (the idempotent alternate-key upsert loop),
  reusable by any OData v4 destination.
- ``runners.dataverse.DataverseInventorySyncRunner`` — combines the two
  bases above and adds only the Dataverse-specific pieces: the
  ``lagsol_inventoryitems`` entity set, the ``lagsol_skuid`` alternate
  key, and the ``lagsol_`` field mapping.
- ``sources.CsvInventorySource`` — the only source-specific piece:
  reading the ERP CSV feed. Composed into the runner here, at the
  entrypoint, rather than inherited — swapping to a different feed
  format for this same Dataverse sync means passing a different
  ``sources.InventorySource`` instance below, with no change to
  ``DataverseInventorySyncRunner`` itself.

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

from runners.dataverse import DataverseInventorySyncRunner
from sources import CsvInventorySource


def main() -> int:
    """Run the full ERP-to-Dataverse inventory sync.

    Returns
    -------
    int
        Process exit code: ``0`` if every record synced without error,
        ``1`` if configuration was invalid, Entra ID authentication failed,
        or any record failed to sync.
    """
    return DataverseInventorySyncRunner(source=CsvInventorySource()).run()


if __name__ == "__main__":
    raise SystemExit(main())
