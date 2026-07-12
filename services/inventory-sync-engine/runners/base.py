"""Inventory-domain record handling, agnostic to both source and write protocol.

Fixes what an inventory record *is* — a deduplicated ``sku_id``,
``item_name``, ``unit_price`` row — and where it comes from, without
assuming a source feed format or a destination wire protocol. This is a
mixin, not a ``BaseSyncRunner`` subclass: it commits to no client type,
so it combines via multiple inheritance with whichever protocol-specific
base (e.g. ``runners.odata.BaseODataInventorySyncRunner``) a destination
leaf class needs, and is reused unchanged by every destination
regardless of write protocol.
"""

import logging

import pandas as pd
from lag_service_kit.dedupe import dedupe_last_seen

from sources import InventorySource

logger: logging.Logger = logging.getLogger(__name__)

DEDUPE_KEY: str = "sku_id"


class InventoryDomainMixin:
    """Source-agnostic, protocol-agnostic inventory record handling.

    Supplies the parts of an inventory sync that never vary regardless
    of which feed produced a record or which wire protocol writes it:
    binding to a composed :class:`sources.InventorySource` and
    deduplicating by SKU. A destination leaf class combines this mixin
    with a protocol-specific base (e.g.
    ``runners.odata.BaseODataInventorySyncRunner``) to get both
    concerns without either one duplicating the other's logic — see
    ``DataverseInventorySyncRunner`` for a concrete example.

    Notes
    -----
    This class deliberately does not inherit
    ``lag_service_kit.runners.base.BaseSyncRunner``: it has no opinion on
    ``ClientT``, ``build_client``, or ``sync_records``, so it never
    participates in that ABC's method-resolution requirements. A
    protocol-specific base supplies those.
    """

    dedupe_key: str = DEDUPE_KEY

    def __init__(self, source: InventorySource) -> None:
        """Bind this run to a source feed.

        Parameters
        ----------
        source : InventorySource
            The feed to read raw inventory records from — e.g. an
            instance of ``sources.CsvInventorySource``. Any object
            satisfying the ``InventorySource`` protocol works, regardless
            of this runner's destination or write protocol.
        """
        self.source = source

    def load_records(self) -> pd.DataFrame:
        """Read this run's source feed and collapse duplicate SKU rows.

        Returns
        -------
        pd.DataFrame
            Deduplicated inventory records, with ``sku_id``, ``item_name``,
            and ``unit_price`` columns.
        """
        return dedupe_last_seen(self.source.read_records(), key=self.dedupe_key)
