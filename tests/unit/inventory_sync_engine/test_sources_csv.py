"""Unit tests for sources.csv.CsvInventorySource.

Covers only ``read_record_chunks`` — ``read_records`` and its
CSV/JSON-equivalence are already covered by the acceptance-level
``test_source_destination_agnostic.py``.
"""

from pathlib import Path

import pandas as pd
import pytest
from lag_service_kit.sources.base import ChunkedRecordSource
from sources.csv import CsvInventorySource
from sources.json import JsonInventorySource

pytestmark = pytest.mark.unit


def _write_csv(path: Path, row_count: int) -> None:
    rows = [
        {"sku_id": f"SKU-{i:03d}", "item_name": "Widget", "unit_price": 1.0}
        for i in range(row_count)
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def test_csv_inventory_source_satisfies_chunked_record_source() -> None:
    """CsvInventorySource structurally satisfies ChunkedRecordSource."""
    assert isinstance(CsvInventorySource(), ChunkedRecordSource)


def test_json_source_does_not_satisfy_chunked_record_source() -> None:
    """JsonInventorySource has no read_record_chunks, by design.

    Proves the optional-capability split actually excludes a format
    that can't stream, rather than every source accidentally satisfying
    ChunkedRecordSource regardless of whether it implements it.
    """
    assert not isinstance(JsonInventorySource(), ChunkedRecordSource)


def test_read_record_chunks_yields_bounded_row_counts(
    tmp_path: Path,
) -> None:
    """read_record_chunks() yields chunks of at most chunksize rows."""
    path = tmp_path / "records.csv"
    _write_csv(path, row_count=5)
    source = CsvInventorySource(csv_path=path)

    chunks = list(source.read_record_chunks(chunksize=2))

    assert [len(chunk) for chunk in chunks] == [2, 2, 1]


def test_read_record_chunks_matches_read_records_when_concatenated(
    tmp_path: Path,
) -> None:
    """Concatenating every chunk reproduces read_records()'s full result."""
    path = tmp_path / "records.csv"
    _write_csv(path, row_count=7)
    source = CsvInventorySource(csv_path=path)

    whole = source.read_records()
    chunked = pd.concat(
        list(source.read_record_chunks(chunksize=3)), ignore_index=True
    )

    assert chunked.equals(whole)


def test_read_record_chunks_raises_file_not_found_for_missing_path(
    tmp_path: Path,
) -> None:
    """Reading a nonexistent CSV path raises FileNotFoundError."""
    source = CsvInventorySource(csv_path=tmp_path / "does-not-exist.csv")

    with pytest.raises(FileNotFoundError):
        source.read_record_chunks(chunksize=10)
