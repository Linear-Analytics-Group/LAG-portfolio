"""Dataverse-specific inventory sync runner.

The only Dataverse-specific knowledge in the inventory sync service lives
here: the ``lagsol_inventoryitems`` entity set, the ``lagsol_skuid``
alternate key, the ``InventorySyncSettings``/``DataverseClient`` wiring,
and the mapping from a generic inventory row to Dataverse's ``lagsol_``
field schema. Everything else is composed from two independent bases:
dedup and source reading from ``runners.base.InventoryDomainMixin``; the
OData v4 upsert loop from ``runners.odata.BaseODataInventorySyncRunner``.
Neither base duplicates the other's logic, and this class adds none of
its own beyond the Dataverse-specific hooks. Source-feed reading is not
inherited at all: the caller passes a ``sources.InventorySource``
instance to the constructor (see ``InventoryDomainMixin.__init__``), so
this same class works unchanged whether the feed is CSV, JSON, Parquet,
or anything else.
"""

from typing import Any, Dict

from config import InventorySyncSettings
from lag_data_utils.clients.dataverse import DataverseClient

from .base import InventoryDomainMixin
from .odata import BaseODataInventorySyncRunner


class DataverseInventorySyncRunner(
    InventoryDomainMixin, BaseODataInventorySyncRunner
):
    """Syncs ERP inventory records into Microsoft Dataverse.

    Notes
    -----
    Takes its source feed as a constructor argument rather than
    inheriting from a source-specific class, since the source feeding a
    given destination can vary independently of the destination itself —
    see ``dataverse_sync_runner.main()``, which pairs this class with
    ``sources.CsvInventorySource``.

    A future destination that also speaks OData v4 (e.g. SAP S/4HANA
    Cloud, SharePoint Online) is added by writing a sibling module —
    ``runners/sap.py`` — with a leaf class combining the same two
    bases (``InventoryDomainMixin``, ``BaseODataInventorySyncRunner``),
    supplying only its own settings, client, entity set, alternate key,
    and field mapping. A future destination that speaks a *different*
    wire protocol (e.g. SOAP) instead combines ``InventoryDomainMixin``
    with a new protocol-specific base (e.g. a future
    ``runners.soap.BaseSoapInventorySyncRunner``) — the dedup and
    source-reading logic in ``InventoryDomainMixin`` is reused either
    way, never duplicated per protocol.
    """

    @property
    def entity_set(self) -> str:
        """Pluralized logical name of the Dataverse inventory entity collection.

        Returns
        -------
        str
            ``"lagsol_inventoryitems"``.
        """
        return "lagsol_inventoryitems"

    @property
    def alternate_key_field(self) -> str:
        """Schema name of the Dataverse alternate key field for a SKU.

        Returns
        -------
        str
            ``"lagsol_skuid"``.
        """
        return "lagsol_skuid"

    def load_settings(self) -> InventorySyncSettings:
        """Load Entra ID and Dataverse settings from the environment/`.env`.

        Returns
        -------
        InventorySyncSettings
            Validated configuration for authenticating against and
            addressing the target Dataverse environment.
        """
        # Required fields are sourced from the environment/`.env` file.
        return InventorySyncSettings()  # type: ignore[call-arg]

    def build_client(self, settings: InventorySyncSettings) -> DataverseClient:
        """Construct a ``DataverseClient`` from validated settings.

        Parameters
        ----------
        settings : InventorySyncSettings
            The settings object returned by :meth:`load_settings`.

        Returns
        -------
        DataverseClient
            A client that authenticates against the configured Dataverse
            environment once
            :meth:`~lag_data_utils.clients.base.BaseClient.acquire_bearer_token`
            is called.
        """
        return DataverseClient.from_settings(settings)

    def build_payload(self, row: Any) -> Dict[str, Any]:
        """Map a generic inventory row to Dataverse's ``lagsol_`` field schema.

        Parameters
        ----------
        row : Any
            A deduplicated inventory row with ``item_name`` and
            ``unit_price`` attributes.

        Returns
        -------
        Dict[str, Any]
            The ``lagsol_name`` and ``lagsol_unitprice`` field values for
            the Dataverse upsert payload.
        """
        return {
            "lagsol_name": row.item_name,
            "lagsol_unitprice": row.unit_price,
        }
