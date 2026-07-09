"""Generic dedup utilities for append-only feed processing."""

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
    return records.drop_duplicates(subset=key, keep="last")
