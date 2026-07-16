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
from defaults import DEDUPE_KEY, DEFAULT_CHUNK_SIZE, DEFAULT_MAX_WORKERS
from lag_data_utils.clients.dataverse import DataverseClient
from sources import InventorySource

from .base import InventoryDomainMixin
from .odata import BaseODataInventorySyncRunner

#: This portfolio's shipped Dataverse schema — a different customer's
#: environment overrides these at construction time (see README.md's
#: "Constructor Injection vs. Environment Bloat").
DEFAULT_ENTITY_SET: str = "lagsol_inventoryitems"
DEFAULT_ALTERNATE_KEY_FIELD: str = "lagsol_skuid"


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
    Cloud, SharePoint Online) is added through a sibling module —
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

    def __init__(
        self,
        source: InventorySource,
        dedupe_key: str = DEDUPE_KEY,
        entity_set: str = DEFAULT_ENTITY_SET,
        alternate_key_field: str = DEFAULT_ALTERNATE_KEY_FIELD,
        max_workers: int = DEFAULT_MAX_WORKERS,
        chunksize: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        """Bind this run to a source feed and its Dataverse schema names.

        Parameters
        ----------
        source : InventorySource
            The feed to read raw inventory records from.
        dedupe_key : str
            The source column uniquely identifying an inventory item.
            Defaults to :data:`~defaults.DEDUPE_KEY`.
        entity_set : str
            The pluralized logical name of the Dataverse inventory
            entity collection. Defaults to :data:`DEFAULT_ENTITY_SET`.
        alternate_key_field : str
            The schema name of the Dataverse alternate key field.
            Defaults to :data:`DEFAULT_ALTERNATE_KEY_FIELD`.
        max_workers : int
            Worker threads used to upsert records concurrently. Forwarded
            to :meth:`~runners.odata.BaseODataInventorySyncRunner.__init__`
            and, via :meth:`build_client`, used to size the destination
            client's HTTP connection pool to match. Defaults to
            :data:`~defaults.DEFAULT_MAX_WORKERS`.
        chunksize : int
            Row count per chunk when ``source`` also satisfies
            ``sources.ChunkedInventorySource``. Forwarded to
            :meth:`~runners.base.InventoryDomainMixin.__init__`. Ignored
            for a source that reads in one shot. Defaults to
            :data:`~defaults.DEFAULT_CHUNK_SIZE`.

        Returns
        -------
        None

        Notes
        -----
        ``dedupe_key`` and ``alternate_key_field`` are independent
        parameters with independent defaults, not one derived from the
        other. They're governed by two unrelated naming authorities:
        ``dedupe_key`` names whichever column a customer's raw source
        feed uses as its record's unique identifier, while
        ``alternate_key_field`` names the field used as the unique
        identifier in the destination — which, for Dataverse, the
        platform *requires* to carry a solution publisher prefix
        (``lagsol_`` here — see
        ``platform/power-platform/.../lagsol_InventoryItem/Entity.xml``).
        These two names structurally cannot coincide in a real
        deployment, so defaulting one from the other would be wrong,
        not merely redundant.
        """
        super().__init__(
            source=source,
            dedupe_key=dedupe_key,
            max_workers=max_workers,
            chunksize=chunksize,
        )
        self._entity_set = entity_set
        self._alternate_key_field = alternate_key_field

    @property
    def entity_set(self) -> str:
        """Pluralized logical name of the Dataverse inventory entity collection.

        Returns
        -------
        str
            The value supplied at construction time (defaults to
            ``"lagsol_inventoryitems"``).
        """
        return self._entity_set

    @property
    def alternate_key_field(self) -> str:
        """Schema name of the Dataverse alternate key field for a SKU.

        Returns
        -------
        str
            The value supplied at construction time (defaults to
            ``"lagsol_skuid"``).
        """
        return self._alternate_key_field

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
            is called. Its HTTP connection pool is sized to twice
            :attr:`_max_workers`, so ``sync_records``'s worker threads
            never queue for a pooled connection.

        Notes
        -----
        Without this, the pool would stay at
        :data:`~lag_data_utils.clients.http.DEFAULT_POOL_MAXSIZE`
        regardless of how many worker threads ``sync_records`` actually
        dispatches, silently capping real concurrency below
        ``max_workers`` once the thread count exceeds the pool size.
        The 2x multiplier — not a bare 1:1 match — keeps headroom above
        the strict worker count: a connection a retry is holding open
        (see :data:`~lag_data_utils.clients.http.DEFAULT_RETRY`) doesn't
        block a different worker from acquiring one of its own, and it
        matches the ratio :data:`~defaults.DEFAULT_MAX_WORKERS` (10)
        already ships against
        :data:`~lag_data_utils.clients.http.DEFAULT_POOL_MAXSIZE` (20).
        """
        return DataverseClient.from_settings(
            settings, pool_maxsize=self._max_workers * 2
        )

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
