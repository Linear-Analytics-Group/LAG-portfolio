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
from typing import Any

import pandas as pd
from lag_service_kit.dedupe import dedupe_last_seen

from defaults import DEDUPE_KEY as DEDUPE_KEY
from sources import InventorySource

logger: logging.Logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        source: InventorySource,
        dedupe_key: str = DEDUPE_KEY,
        **kwargs: Any,
    ) -> None:
        """Bind this run to a source feed and its business-key column.

        Parameters
        ----------
        source : InventorySource
            The feed to read raw inventory records from — e.g. an
            instance of ``sources.CsvInventorySource``. Any object
            satisfying the ``InventorySource`` protocol works, regardless
            of this runner's destination or write protocol.
        dedupe_key : str
            The column name in ``source``'s records that uniquely
            identifies an inventory item — ``"sku_id"`` for the shipped
            mock feed. A customer whose source feed names this column
            differently overrides it here at construction time rather
            than forking this mixin; see README.md's "Constructor
            Injection vs. Environment Bloat" for why this is a
            constructor argument and not an environment variable.
        **kwargs : Any
            Forwarded, unexamined, to ``super().__init__()`` — see Notes.

        Notes
        -----
        Calls ``super().__init__(**kwargs)`` even though this mixin has
        no explicit base of its own, because it doesn't know in advance
        what it will be mixed with — a destination leaf class combines
        it with a protocol-specific base via multiple inheritance (see
        ``DataverseInventorySyncRunner``). Skipping this call would
        break that base's own ``__init__`` for every destination built
        this way, with no error to signal it. Accepting and forwarding
        ``**kwargs`` (rather than calling ``super().__init__()`` with no
        arguments) lets a leaf class configure *any* base in the chain
        — e.g. ``BaseODataInventorySyncRunner``'s ``max_workers`` —
        through one constructor call, without this domain-only mixin
        needing to know that parameter's name.
        """
        super().__init__(**kwargs)
        self.source = source
        self.dedupe_key = dedupe_key

    def load_records(self) -> pd.DataFrame:
        """Read this run's source feed and collapse duplicate SKU rows.

        Returns
        -------
        pd.DataFrame
            Deduplicated inventory records, with ``sku_id``, ``item_name``,
            and ``unit_price`` columns.
        """
        return dedupe_last_seen(self.source.read_records(), key=self.dedupe_key)
