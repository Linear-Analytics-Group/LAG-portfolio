"""Record-domain source contract: format-agnostic feed reading.

Fixes what it means to supply records to a sync run —
:meth:`RecordSource.read_records` — without assuming CSV, JSON,
Parquet, or any other feed format, and without assuming any
particular record schema. A sync runner's domain mixin (e.g.
``InventoryDomainMixin`` in a service's own ``runners/base.py``)
composes one of these at construction time, so a destination-specific
runner never inherits from, or otherwise hardcodes, a particular
source format.

One layer below this, :class:`~lag_service_kit.readers.base.RecordReader`
fixes how one *file format* becomes a DataFrame at all (CSV, JSON,
Parquet); this Protocol fixes how a *source* is composed into a runner,
regardless of which reader (if any) it wraps.
"""

from typing import Iterator, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class RecordSource(Protocol):
    """Structural contract for a component supplying raw records.

    Any object implementing ``read_records`` satisfies this protocol,
    regardless of the underlying feed format or record schema. A sync
    runner should depend only on this contract — never on a concrete
    source class or a specific file format — so that pairing a
    destination with a new source format never requires changing the
    runner's own code.
    """

    def read_records(self) -> pd.DataFrame:
        """Read raw, not-yet-deduplicated records.

        Returns
        -------
        pd.DataFrame
            Raw records, with whatever columns the calling domain
            mixin's business schema expects (e.g. ``sku_id``,
            ``item_name``, ``unit_price`` for an inventory service).
        """
        ...


@runtime_checkable
class ChunkedRecordSource(Protocol):
    """Structural contract for a source that can stream records in chunks.

    A separate, optional capability from ``RecordSource`` rather than
    a method added to it: whether a feed format can be read in bounded
    memory varies independently of whether it can be read at all (CSV's
    line-delimited structure allows true streaming; a single JSON array
    or an as-yet-unsupported format may not). A domain layer (e.g.
    ``InventoryDomainMixin``) checks
    ``isinstance(source, ChunkedRecordSource)`` at runtime and only
    takes the chunked path when the bound source actually supports it,
    falling back to ``RecordSource.read_records()`` otherwise.
    """

    def read_record_chunks(self, chunksize: int) -> Iterator[pd.DataFrame]:
        """Read raw, not-yet-deduplicated records in chunks.

        Parameters
        ----------
        chunksize : int
            Maximum number of rows per yielded chunk.

        Returns
        -------
        Iterator[pd.DataFrame]
            Successive row chunks in file order, with whatever columns
            the calling domain mixin's business schema expects.
        """
        ...
