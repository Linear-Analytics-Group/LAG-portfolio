"""Unit tests for lag_service_kit.dedupe."""

import pandas as pd
import pytest
from lag_service_kit.dedupe import dedupe_last_seen, dedupe_last_seen_chunks

pytestmark = pytest.mark.unit


def test_last_occurrence_wins_for_a_duplicated_key() -> None:
    """When a key repeats, the last row for that key in file order is kept."""
    records = pd.DataFrame(
        [
            {"sku_id": "SKU-001", "unit_price": 9.99},
            {"sku_id": "SKU-001", "unit_price": 19.99},
        ]
    )

    deduped = dedupe_last_seen(records, key="sku_id")

    assert len(deduped) == 1
    assert deduped.iloc[0]["unit_price"] == 19.99


def test_records_with_no_duplicates_are_unchanged() -> None:
    """A feed with no repeated keys passes through with every row kept."""
    records = pd.DataFrame(
        [
            {"sku_id": "SKU-001", "unit_price": 9.99},
            {"sku_id": "SKU-002", "unit_price": 19.99},
        ]
    )

    deduped = dedupe_last_seen(records, key="sku_id")

    assert len(deduped) == 2


def test_other_columns_are_preserved_alongside_the_winning_row() -> None:
    """Deduping by one key column keeps every other column's winning value."""
    records = pd.DataFrame(
        [
            {"sku_id": "SKU-001", "item_name": "Widget", "unit_price": 9.99},
            {
                "sku_id": "SKU-001",
                "item_name": "Widget (updated)",
                "unit_price": 12.50,
            },
        ]
    )

    deduped = dedupe_last_seen(records, key="sku_id")

    assert deduped.iloc[0]["item_name"] == "Widget (updated)"
    assert deduped.iloc[0]["unit_price"] == 12.50


def test_chunks_last_occurrence_wins_across_a_chunk_boundary() -> None:
    """A key's later occurrence wins even when it's in a later chunk.

    This is the one property that would silently regress if chunk
    boundaries were ever treated as independent dedup scopes instead of
    one continuous last-seen scan.
    """
    chunk_one = pd.DataFrame([{"sku_id": "SKU-001", "unit_price": 9.99}])
    chunk_two = pd.DataFrame([{"sku_id": "SKU-001", "unit_price": 19.99}])

    deduped = dedupe_last_seen_chunks([chunk_one, chunk_two], key="sku_id")

    assert len(deduped) == 1
    assert deduped.iloc[0]["unit_price"] == 19.99


def test_chunks_with_no_duplicates_are_unchanged() -> None:
    """Non-duplicated keys spread across chunks all survive."""
    chunk_one = pd.DataFrame([{"sku_id": "SKU-001", "unit_price": 9.99}])
    chunk_two = pd.DataFrame([{"sku_id": "SKU-002", "unit_price": 19.99}])

    deduped = dedupe_last_seen_chunks([chunk_one, chunk_two], key="sku_id")

    assert len(deduped) == 2


def test_chunks_matches_the_whole_dataframe_equivalent() -> None:
    """Chunking the same rows produces the same result as one DataFrame."""
    rows = [
        {"sku_id": "SKU-001", "unit_price": 9.99},
        {"sku_id": "SKU-002", "unit_price": 4.00},
        {"sku_id": "SKU-001", "unit_price": 12.50},
    ]
    whole = dedupe_last_seen(pd.DataFrame(rows), key="sku_id")
    chunked = dedupe_last_seen_chunks(
        [pd.DataFrame([row]) for row in rows], key="sku_id"
    )

    assert (
        chunked.sort_values("sku_id")
        .reset_index(drop=True)
        .equals(whole.sort_values("sku_id").reset_index(drop=True))
    )


def test_chunks_with_no_chunks_returns_an_empty_dataframe() -> None:
    """An empty iterator of chunks returns an empty DataFrame, not an error."""
    deduped = dedupe_last_seen_chunks([], key="sku_id")

    assert len(deduped) == 0


def test_chunks_with_only_empty_chunks_preserves_columns() -> None:
    """All-empty chunks still yield a DataFrame with the right columns."""
    empty_chunk = pd.DataFrame(columns=["sku_id", "unit_price"])

    deduped = dedupe_last_seen_chunks([empty_chunk], key="sku_id")

    assert len(deduped) == 0
    assert list(deduped.columns) == ["sku_id", "unit_price"]
