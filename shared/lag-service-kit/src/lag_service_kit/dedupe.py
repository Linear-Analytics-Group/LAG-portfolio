"""Generic dedup utilities for append-only feed processing."""

from typing import Any, Iterable, Optional

import pandas as pd


def dedupe_last_seen(records: pd.DataFrame, key: str) -> pd.DataFrame:
    """Collapse duplicate rows to their last-seen value for a given key column.

    Parameters
    ----------
    records : pd.DataFrame
        Records to deduplicate, potentially containing multiple rows per
        ``key`` value.
    key : str
        Name of the column identifying a unique record. When a value
        appears more than once, the last row for that value in file order
        is kept, treating ``records`` as an append-only stream where later
        rows supersede earlier ones.

    Returns
    -------
    pd.DataFrame
        One row per unique ``key`` value.
    """
    # pandas-stubs types drop_duplicates() as Any; the explicit
    # annotation asserts the real return type mypy --strict needs.
    deduped: pd.DataFrame = records.drop_duplicates(
        subset=key, keep="last"
    )
    return deduped


def dedupe_last_seen_chunks(
    chunks: Iterable[pd.DataFrame], key: str
) -> pd.DataFrame:
    """Collapse duplicate rows to their last-seen value across many chunks.

    The chunked equivalent of :func:`dedupe_last_seen`: reads each chunk
    in turn, keeping only the most recently seen row per ``key`` value in
    a plain dict rather than concatenating every chunk into one
    in-memory DataFrame first. Memory scales with the number of unique
    ``key`` values seen so far, not with the total row count — the
    property that makes chunked reading (see
    ``lag_service_kit.readers.csv.CsvRecordReader.load_chunks``)
    actually bound memory for a large append-only feed, rather than just
    moving the same whole-file materialization one step later.

    Parameters
    ----------
    chunks : Iterable[pd.DataFrame]
        Successive slices of one logical record set, in file order — a
        duplicate ``key`` value in a later chunk supersedes its
        occurrence in an earlier one, exactly as if the chunks had first
        been concatenated and passed to :func:`dedupe_last_seen`.
    key : str
        Name of the column identifying a unique record.

    Returns
    -------
    pd.DataFrame
        One row per unique ``key`` value, with the same columns as the
        input chunks — even when ``chunks`` is empty or every chunk has
        zero rows, in which case an empty, correctly-columned DataFrame
        is returned rather than one with no columns at all.
    """
    latest_by_key: dict[Any, Any] = {}
    columns: Optional[list[str]] = None

    for chunk in chunks:
        if columns is None:
            columns = list(chunk.columns)
        for row in chunk.itertuples(index=False):
            latest_by_key[getattr(row, key)] = row

    # pandas-stubs types the DataFrame constructor as Any; the explicit
    # annotations assert the real return type mypy --strict needs.
    if not latest_by_key:
        empty: pd.DataFrame = pd.DataFrame(columns=columns or [])
        return empty
    deduped: pd.DataFrame = pd.DataFrame(latest_by_key.values())
    return deduped
