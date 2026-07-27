"""Dataverse-specific inventory sync runner.

The only Dataverse-specific knowledge in the inventory sync service lives
here: the ``lagsol_inventoryitems`` entity set, the ``lagsol_skuid``
alternate key, the ``InventorySyncSettings``/``DataverseClient`` wiring,
and the mapping from a generic inventory row to Dataverse's ``lagsol_``
field schema. Everything else is composed from two independent bases:
dedup and source reading from ``runners.base.InventoryDomainMixin``
(inventory-domain, stays in this service); the OData v4 upsert loop
from ``lag_service_kit.runners.odata.BaseODataSyncRunner``
(destination/domain-agnostic, shared scaffolding). Neither base
duplicates the other's logic, and this class adds none of its own
beyond the Dataverse-specific hooks. Source-feed reading is not
inherited at all: the caller passes a
``lag_service_kit.sources.base.RecordSource`` instance to the
constructor (see ``InventoryDomainMixin.__init__``), so this same
class works unchanged whether the feed is CSV, JSON, Parquet, or
anything else.
"""

from typing import Any

from config import InventorySyncSettings
from defaults import (
    DEDUPE_KEY,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_FAILURE_THRESHOLD,
    DEFAULT_MAX_WORKERS,
    DEFAULT_WRITE_WINDOW_SIZE,
)
from lag_data_utils.clients.dataverse import DataverseClient
from lag_service_kit.runners.odata import BaseODataSyncRunner
from lag_service_kit.sources.base import RecordSource
from runners.base import InventoryDomainMixin

#: This portfolio's shipped Dataverse schema — a different customer's
#: environment overrides these at construction time (see README.md's
#: "Constructor Injection vs. Environment Bloat").
DEFAULT_ENTITY_SET: str = "lagsol_inventoryitems"
DEFAULT_ALTERNATE_KEY_FIELD: str = "lagsol_skuid"

#: Source column name -> Dataverse field name. Data, not logic: a
#: different customer's field names override this whole dict at
#: construction time rather than requiring a ``build_payload()``
#: override — see README.md's "Field Mapping: Constructor-Injected
#: Dict vs. External Mapping File".
DEFAULT_FIELD_MAPPING: dict[str, str] = {
    "item_name": "lagsol_name",
    "unit_price": "lagsol_unitprice",
}


class DataverseInventorySyncRunner(InventoryDomainMixin, BaseODataSyncRunner):
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
    bases (``InventoryDomainMixin``,
    ``lag_service_kit.runners.odata.BaseODataSyncRunner``), supplying
    only its own settings, client, entity set, alternate key, and field
    mapping. A future destination that speaks a *different* wire
    protocol (e.g. SOAP) instead combines ``InventoryDomainMixin`` with
    a new protocol-specific base (e.g. a future
    ``lag_service_kit.runners.soap.BaseSoapSyncRunner``, promoted to
    shared scaffolding the same way ``BaseODataSyncRunner`` already is)
    — the dedup and source-reading logic in ``InventoryDomainMixin`` is
    reused either way, never duplicated per protocol.
    """

    def __init__(
        self,
        source: RecordSource,
        dedupe_key: str = DEDUPE_KEY,
        entity_set: str = DEFAULT_ENTITY_SET,
        alternate_key_field: str = DEFAULT_ALTERNATE_KEY_FIELD,
        field_mapping: dict[str, str] = DEFAULT_FIELD_MAPPING,
        max_workers: int = DEFAULT_MAX_WORKERS,
        chunksize: int = DEFAULT_CHUNK_SIZE,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        write_window_size: int = DEFAULT_WRITE_WINDOW_SIZE,
    ) -> None:
        """Bind this run to a source feed and its Dataverse schema names.

        Parameters
        ----------
        source : RecordSource
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
        field_mapping : dict[str, str]
            Source column name -> Dataverse field name, applied
            generically by :meth:`build_payload`. Defaults to
            :data:`DEFAULT_FIELD_MAPPING`.
        max_workers : int
            Worker threads used to upsert records concurrently. Forwarded
            to
            :meth:`~lag_service_kit.runners.odata.BaseODataSyncRunner.__init__`
            and, via :meth:`build_client`, used to size the destination
            client's HTTP connection pool to match. Defaults to
            :data:`~defaults.DEFAULT_MAX_WORKERS`.
        chunksize : int
            Row count per chunk when ``source`` also satisfies
            ``lag_service_kit.sources.base.ChunkedRecordSource``.
            Forwarded to
            :meth:`~runners.base.InventoryDomainMixin.__init__`. Ignored
            for a source that reads in one shot. Defaults to
            :data:`~defaults.DEFAULT_CHUNK_SIZE`.
        failure_threshold : int
            Consecutive upsert failures that trip
            ``BaseODataSyncRunner.sync_records``'s circuit breaker.
            Forwarded to ``BaseODataSyncRunner.__init__``. Defaults to
            :data:`~defaults.DEFAULT_FAILURE_THRESHOLD`.
        write_window_size : int
            Maximum upsert futures
            ``BaseODataSyncRunner.sync_records`` holds in memory at
            once. Forwarded to ``BaseODataSyncRunner.__init__``.
            Defaults to :data:`~defaults.DEFAULT_WRITE_WINDOW_SIZE`.
            Should be at least ``max_workers``, or some workers will
            sit idle with no queued task — not validated here or in
            ``BaseODataSyncRunner.__init__``, so passing a smaller
            value silently degrades concurrency rather than raising an
            error; see ``defaults.DEFAULT_WRITE_WINDOW_SIZE``'s own
            docstring for why.

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
            failure_threshold=failure_threshold,
            write_window_size=write_window_size,
        )
        self._entity_set = entity_set
        self._alternate_key_field = alternate_key_field
        self._field_mapping = field_mapping

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
        return InventorySyncSettings()

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

    def build_payload(self, row: Any) -> dict[str, Any]:
        """Map a generic inventory row to Dataverse's field schema.

        Applies :attr:`_field_mapping` generically rather than naming
        source or destination fields here directly — the field names
        themselves are data, supplied at construction time (see
        :data:`DEFAULT_FIELD_MAPPING`), not logic hardcoded into this
        method. See README.md's "Field Mapping: Constructor-Injected
        Dict vs. External Mapping File" for why.

        Parameters
        ----------
        row : Any
            A deduplicated inventory row exposing every source column
            name in :attr:`_field_mapping` as an attribute.

        Returns
        -------
        dict[str, Any]
            One key per :attr:`_field_mapping` value (a Dataverse field
            name), holding the corresponding source column's value from
            ``row``.
        """
        return {
            dataverse_field: getattr(row, source_column)
            for source_column, dataverse_field in self._field_mapping.items()
        }
