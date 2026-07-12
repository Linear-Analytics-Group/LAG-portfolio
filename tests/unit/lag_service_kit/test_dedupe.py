"""Unit tests for lag_service_kit.dedupe.dedupe_last_seen."""

import pandas as pd
import pytest
from lag_service_kit.dedupe import dedupe_last_seen

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
    """Deduping by one key column keeps every other column's value for the winning row."""
    records = pd.DataFrame(
        [
            {"sku_id": "SKU-001", "item_name": "Widget", "unit_price": 9.99},
            {"sku_id": "SKU-001", "item_name": "Widget (updated)", "unit_price": 12.50},
        ]
    )

    deduped = dedupe_last_seen(records, key="sku_id")

    assert deduped.iloc[0]["item_name"] == "Widget (updated)"
    assert deduped.iloc[0]["unit_price"] == 12.50
