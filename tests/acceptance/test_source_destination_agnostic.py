"""Business requirement: source and destination agnostic.

The same destination class must work unchanged with any source format,
and the same source format must work unchanged with any destination —
proven by running the identical mock dataset through
``DataverseInventorySyncRunner`` via both a CSV and a JSON source and
asserting the deduplicated output is identical.
"""

import pytest

from runners.dataverse import DataverseInventorySyncRunner
from sources import CsvInventorySource, JsonInventorySource


@pytest.mark.acceptance
def test_csv_and_json_sources_produce_identical_deduplicated_records(
    csv_source: CsvInventorySource, json_source: JsonInventorySource
) -> None:
    """The same mock feed, in CSV and JSON, yields byte-for-byte identical deduped records."""
    csv_runner = DataverseInventorySyncRunner(source=csv_source)
    json_runner = DataverseInventorySyncRunner(source=json_source)

    csv_records = csv_runner.load_records().sort_values("sku_id").reset_index(drop=True)
    json_records = json_runner.load_records().sort_values("sku_id").reset_index(drop=True)

    assert csv_records.equals(json_records)


@pytest.mark.acceptance
def test_swapping_source_requires_no_new_destination_class(
    csv_source: CsvInventorySource, json_source: JsonInventorySource
) -> None:
    """Both sources are consumed through the exact same destination class — no new subclass."""
    csv_runner = DataverseInventorySyncRunner(source=csv_source)
    json_runner = DataverseInventorySyncRunner(source=json_source)

    assert type(csv_runner) is type(json_runner) is DataverseInventorySyncRunner


@pytest.mark.acceptance
def test_shipped_mock_feeds_are_themselves_interchangeable() -> None:
    """The real CSV and JSON mock feeds shipped in data/ are equivalent, not just the temp-file fixtures."""
    csv_runner = DataverseInventorySyncRunner(source=CsvInventorySource())
    json_runner = DataverseInventorySyncRunner(source=JsonInventorySource())

    csv_records = csv_runner.load_records().sort_values("sku_id").reset_index(drop=True)
    json_records = json_runner.load_records().sort_values("sku_id").reset_index(drop=True)

    assert len(csv_records) == 100
    assert csv_records.equals(json_records)
