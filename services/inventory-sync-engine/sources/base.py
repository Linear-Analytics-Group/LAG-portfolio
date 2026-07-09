"""Inventory-domain source contract: format-agnostic feed reading.

Fixes what it means to supply inventory records to a sync run —
:meth:`InventorySource.read_records` — without assuming CSV, JSON,
Parquet, or any other feed format. A sync runner (e.g.
``runners.base.InventoryDomainMixin``) composes one of these at
construction time, so a destination-specific runner (e.g.
``DataverseInventorySyncRunner``) never inherits from, or otherwise
hardcodes, a particular source format.
"""

from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class InventorySource(Protocol):
    """Structural contract for a component supplying raw inventory records.

    Any object implementing ``read_records`` satisfies this protocol,
    regardless of the underlying feed format. A sync runner should depend
    only on this contract — never on a concrete source class or a
    specific file format — so that pairing a destination with a new
    source format never requires changing the runner's own code.
    """

    def read_records(self) -> pd.DataFrame:
        """Read raw, not-yet-deduplicated inventory records.

        Returns
        -------
        pd.DataFrame
            Raw inventory records with ``sku_id``, ``item_name``, and
            ``unit_price`` columns.
        """
        ...
