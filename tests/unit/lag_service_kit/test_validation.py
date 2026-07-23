"""Unit tests for lag_service_kit.validation.

Covers require_columns and require_non_null in isolation, with no
dependency on any concrete service's schema.
"""

import pandas as pd
import pytest
from lag_service_kit.validation import (
    RecordValidationError,
    require_columns,
    require_non_null,
)

pytestmark = pytest.mark.unit


def test_require_columns_passes_when_every_column_is_present() -> None:
    """No error when every required column exists, regardless of order."""
    records = pd.DataFrame(
        [{"sku_id": "A", "item_name": "Widget", "unit_price": 9.99}]
    )

    require_columns(records, ["unit_price", "sku_id"])


def test_require_columns_raises_naming_every_missing_column() -> None:
    """A single error lists every missing column, not just the first."""
    records = pd.DataFrame([{"sku_id": "A"}])

    with pytest.raises(RecordValidationError) as exc_info:
        require_columns(records, ["sku_id", "warehouse_code", "reorder_point"])

    message = str(exc_info.value)
    assert "warehouse_code" in message
    assert "reorder_point" in message
    assert "sku_id" not in message


def test_require_non_null_passes_when_every_value_is_real() -> None:
    """No error when every row has a real, non-blank value."""
    records = pd.DataFrame([{"sku_id": "SKU-001"}, {"sku_id": "SKU-002"}])

    require_non_null(records, "sku_id")


def test_require_non_null_raises_on_a_null_value() -> None:
    """A None/NaN value raises, naming the column and offending count."""
    records = pd.DataFrame([{"sku_id": "SKU-001"}, {"sku_id": None}])

    with pytest.raises(RecordValidationError) as exc_info:
        require_non_null(records, "sku_id")

    message = str(exc_info.value)
    assert "sku_id" in message
    assert "1 row" in message


def test_require_non_null_raises_on_a_blank_string() -> None:
    """A whitespace-only value is treated the same as null, not skipped."""
    records = pd.DataFrame([{"sku_id": "SKU-001"}, {"sku_id": "   "}])

    with pytest.raises(RecordValidationError):
        require_non_null(records, "sku_id")


def test_require_non_null_reports_the_exact_offending_count() -> None:
    """Multiple offending rows are all counted, not just detected."""
    records = pd.DataFrame(
        [
            {"sku_id": "SKU-001"},
            {"sku_id": None},
            {"sku_id": ""},
            {"sku_id": "SKU-002"},
        ]
    )

    with pytest.raises(RecordValidationError) as exc_info:
        require_non_null(records, "sku_id")

    assert "2 row" in str(exc_info.value)
