"""Inventory-domain source contract: format-agnostic feed reading.

Fixes what it means to supply inventory records to a sync run —
:meth:`InventorySource.read_records` — without assuming CSV, JSON,
Parquet, or any other feed format. A sync runner (e.g.
``runners.base.InventoryDomainMixin``) composes one of these at
construction time, so a destination-specific runner (e.g.
``DataverseInventorySyncRunner``) never inherits from, or otherwise
hardcodes, a particular source format.
"""

from typing import Iterator, Protocol, runtime_checkable

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


@runtime_checkable
class ChunkedInventorySource(Protocol):
    """Structural contract for a source that can stream records in chunks.

    A separate, optional capability from ``InventorySource`` rather than
    a method added to it: whether a feed format can be read in bounded
    memory varies independently of whether it can be read at all (CSV's
    line-delimited structure allows true streaming; a single JSON array
    or an as-yet-unsupported format may not). A domain layer (e.g.
    ``runners.base.InventoryDomainMixin``) checks
    ``isinstance(source, ChunkedInventorySource)`` at runtime and only
    takes the chunked path when the bound source actually supports it,
    falling back to ``InventorySource.read_records()`` otherwise.
    """

    def read_record_chunks(self, chunksize: int) -> Iterator[pd.DataFrame]:
        """Read raw, not-yet-deduplicated inventory records in chunks.

        Parameters
        ----------
        chunksize : int
            Maximum number of rows per yielded chunk.

        Returns
        -------
        Iterator[pd.DataFrame]
            Successive row chunks in file order, each with ``sku_id``,
            ``item_name``, and ``unit_price`` columns.
        """
        ...
