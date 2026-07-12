"""Unit tests for lag_service_kit.readers.

Covers CsvRecordReader, JsonRecordReader, ParquetRecordReader.

Each reader is tested against the same logical record set, in its own
format, confirming all three satisfy the ``RecordReader`` protocol
identically from the caller's point of view.
"""

from pathlib import Path
from typing import Type

import pandas as pd
import pytest
from lag_service_kit.readers import (
    CsvRecordReader,
    JsonRecordReader,
    ParquetRecordReader,
    RecordReader,
)

pytestmark = pytest.mark.unit

SAMPLE_RECORDS = [
    {"sku_id": "SKU-001", "item_name": "Widget", "unit_price": 9.99},
    {"sku_id": "SKU-002", "item_name": "Gadget", "unit_price": 19.99},
]


def test_csv_record_reader_loads_expected_columns_and_values(
    tmp_path: Path,
) -> None:
    """CsvRecordReader loads a CSV into a DataFrame with expected values."""
    path = tmp_path / "records.csv"
    pd.DataFrame(SAMPLE_RECORDS).to_csv(path, index=False)

    df = CsvRecordReader().load(path)

    assert list(df.columns) == ["sku_id", "item_name", "unit_price"]
    assert len(df) == 2
    assert df.iloc[0]["sku_id"] == "SKU-001"


def test_csv_record_reader_raises_file_not_found_for_missing_path(
    tmp_path: Path,
) -> None:
    """Reading a nonexistent CSV path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        CsvRecordReader().load(tmp_path / "does-not-exist.csv")


def test_json_record_reader_loads_orient_records_layout(
    tmp_path: Path,
) -> None:
    """JsonRecordReader loads an orient='records' array into a DataFrame."""
    path = tmp_path / "records.json"
    pd.DataFrame(SAMPLE_RECORDS).to_json(path, orient="records")

    df = JsonRecordReader().load(path)

    assert list(df.columns) == ["sku_id", "item_name", "unit_price"]
    assert len(df) == 2
    assert df.iloc[1]["sku_id"] == "SKU-002"


def test_json_record_reader_raises_file_not_found_for_missing_path(
    tmp_path: Path,
) -> None:
    """Reading a nonexistent JSON path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        JsonRecordReader().load(tmp_path / "does-not-exist.json")


def test_parquet_record_reader_loads_expected_columns_and_values(
    tmp_path: Path,
) -> None:
    """ParquetRecordReader loads a Parquet file with expected values."""
    path = tmp_path / "records.parquet"
    pd.DataFrame(SAMPLE_RECORDS).to_parquet(path)

    df = ParquetRecordReader().load(path)

    assert list(df.columns) == ["sku_id", "item_name", "unit_price"]
    assert len(df) == 2


def test_parquet_record_reader_raises_file_not_found_for_missing_path(
    tmp_path: Path,
) -> None:
    """Reading a nonexistent Parquet path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        ParquetRecordReader().load(tmp_path / "does-not-exist.parquet")


@pytest.mark.parametrize(
    "reader_cls", [CsvRecordReader, JsonRecordReader, ParquetRecordReader]
)
def test_every_reader_satisfies_the_record_reader_protocol(
    reader_cls: Type[RecordReader],
) -> None:
    """Every shipped reader structurally satisfies RecordReader."""
    assert isinstance(reader_cls(), RecordReader)
