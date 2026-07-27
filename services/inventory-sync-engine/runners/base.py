"""Inventory-domain record handling, agnostic to both source and write protocol.

Fixes what an inventory record *is* — a deduplicated ``sku_id``,
``item_name``, ``unit_price`` row — and where it comes from, without
assuming a source feed format or a destination wire protocol. This is a
mixin, not a ``BaseSyncRunner`` subclass: it commits to no client type,
so it combines via multiple inheritance with whichever protocol-specific
base (e.g. ``lag_service_kit.runners.odata.BaseODataSyncRunner``) a
destination leaf class needs, and is reused unchanged by every
destination regardless of write protocol.
"""

import logging
from typing import Any, Iterator

import pandas as pd
from lag_service_kit.dedupe import dedupe_last_seen, dedupe_last_seen_chunks
from lag_service_kit.sources.base import ChunkedRecordSource, RecordSource
from lag_service_kit.validation import require_columns, require_non_null

from defaults import DEDUPE_KEY as DEDUPE_KEY
from defaults import DEFAULT_CHUNK_SIZE
from defaults import DEFAULT_REQUIRED_COLUMNS as DEFAULT_REQUIRED_COLUMNS

logger: logging.Logger = logging.getLogger(__name__)


class InventoryDomainMixin:
    """Source-agnostic, protocol-agnostic inventory record handling.

    Supplies the parts of an inventory sync that never vary regardless
    of which feed produced a record or which wire protocol writes it:
    binding to a composed
    :class:`~lag_service_kit.sources.base.RecordSource` and
    deduplicating by the key provided. A destination leaf class combines
    this mixin with a protocol-specific base (e.g.
    ``lag_service_kit.runners.odata.BaseODataSyncRunner``) to get both
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
        source: RecordSource,
        dedupe_key: str = DEDUPE_KEY,
        chunksize: int = DEFAULT_CHUNK_SIZE,
        required_columns: tuple[str, ...] = DEFAULT_REQUIRED_COLUMNS,
        **kwargs: Any,
    ) -> None:
        """Bind this run to a source feed and its business-key column.

        Parameters
        ----------
        source : RecordSource
            The feed to read raw inventory records from — e.g. an
            instance of ``sources.CsvInventorySource``. Any object
            satisfying the ``RecordSource`` protocol works, regardless
            of this runner's destination or write protocol.
        dedupe_key : str
            The column name in ``source``'s records that uniquely
            identifies an inventory item — e.g., ``"sku_id"`` for the
            shipped mock feed. A customer whose source feed names this column
            differently overrides it here at construction time rather
            than forking this mixin; see README.md's "Constructor
            Injection vs. Environment Bloat" for why this is a
            constructor argument and not an environment variable.
        chunksize : int
            Row count per chunk when ``source`` also satisfies
            ``lag_service_kit.sources.base.ChunkedRecordSource``.
            Ignored otherwise. Defaults to
            :data:`~defaults.DEFAULT_CHUNK_SIZE`.
        required_columns : tuple[str, ...]
            Column names (besides ``dedupe_key``, always required
            separately) that every record read from ``source`` must
            carry. Checked by :meth:`load_records` before dedup, so a
            malformed feed raises a clear
            ``lag_service_kit.validation.RecordValidationError``
            naming what's missing instead of an opaque failure deeper
            in dedup or the destination write. Defaults to
            :data:`~defaults.DEFAULT_REQUIRED_COLUMNS`.
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
        — e.g. ``BaseODataSyncRunner``'s ``max_workers`` —
        through one constructor call, without this domain-only mixin
        needing to know that parameter's name.
        """
        super().__init__(**kwargs)
        self.source = source
        self.dedupe_key = dedupe_key
        self.chunksize = chunksize
        self.required_columns = required_columns

    def _validate(self, records: pd.DataFrame) -> pd.DataFrame:
        """Check one batch of raw records against this run's schema.

        Parameters
        ----------
        records : pd.DataFrame
            Records read from :attr:`source`, not yet deduplicated —
            a full read, or one chunk of a chunked read.

        Returns
        -------
        pd.DataFrame
            ``records``, unchanged — returned only so this method
            composes into a chunk-generator pipeline (see
            :meth:`load_records`).

        Raises
        ------
        lag_service_kit.validation.RecordValidationError
            If ``dedupe_key`` or any of :attr:`required_columns` is
            missing, or if any row's ``dedupe_key`` value is null or
            blank. Checked in that order, so a missing column is
            always reported before a null-value check that could not
            otherwise run against a column that isn't there.
        """
        require_columns(records, [self.dedupe_key, *self.required_columns])
        require_non_null(records, self.dedupe_key)
        return records

    def _validated_chunks(
        self, chunks: Iterator[pd.DataFrame]
    ) -> Iterator[pd.DataFrame]:
        """Validate each chunk of a chunked read as it arrives.

        Parameters
        ----------
        chunks : Iterator[pd.DataFrame]
            Successive row chunks from
            ``ChunkedRecordSource.read_record_chunks``.

        Returns
        -------
        Iterator[pd.DataFrame]
            The same chunks, each checked via :meth:`_validate` before
            being yielded — so a malformed chunk raises before any
            chunk after it is even read from the source, and before
            ``dedupe_last_seen_chunks`` ever sees it.
        """
        for chunk in chunks:
            yield self._validate(chunk)

    def load_records(self) -> pd.DataFrame:
        """Read this run's source feed and collapse duplicate SKU rows.

        Returns
        -------
        pd.DataFrame
            Deduplicated inventory records, with ``sku_id``, ``item_name``,
            and ``unit_price`` columns.

        Raises
        ------
        lag_service_kit.validation.RecordValidationError
            If the records read from :attr:`source` are missing
            ``dedupe_key`` or any of :attr:`required_columns`, or if
            any row's ``dedupe_key`` value is null or blank — before
            dedup ever runs, so a malformed feed fails with a clear,
            specific message instead of a ``KeyError`` deep inside
            ``pandas.DataFrame.drop_duplicates`` or a bad alternate-key
            value reaching the destination write.

        Notes
        -----
        When :attr:`source` also satisfies
        ``lag_service_kit.sources.base.ChunkedRecordSource``, reads and
        dedupes it in :attr:`chunksize`-row chunks via
        ``lag_service_kit.dedupe.dedupe_last_seen_chunks`` — bounding
        memory to roughly one chunk plus one row per unique
        :attr:`dedupe_key` value, rather than the whole file at once.
        Falls back to a single ``read_records()`` call otherwise, since
        not every source format can stream (see
        ``ChunkedRecordSource``'s docstring).
        """
        if isinstance(self.source, ChunkedRecordSource):
            chunks = self.source.read_record_chunks(self.chunksize)
            return dedupe_last_seen_chunks(
                self._validated_chunks(chunks), key=self.dedupe_key
            )
        records = self._validate(self.source.read_records())
        return dedupe_last_seen(records, key=self.dedupe_key)
