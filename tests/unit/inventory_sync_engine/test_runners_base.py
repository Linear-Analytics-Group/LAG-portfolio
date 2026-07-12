"""Unit tests for runners.base.InventoryDomainMixin.

``InventoryDomainMixin`` does not inherit ``BaseSyncRunner`` and commits
to no client type, so it's instantiated directly here — no destination
leaf class is needed to test its dedup/source-binding behavior in
isolation.
"""

import pandas as pd
from runners.base import DEDUPE_KEY, InventoryDomainMixin


class _StubSource:
    """A minimal InventorySource test double returning a fixed DataFrame."""

    def __init__(self, records: pd.DataFrame) -> None:
        self._records = records

    def read_records(self) -> pd.DataFrame:
        return self._records


def test_default_dedupe_key_is_sku_id():
    """The mixin's default dedupe_key matches the inventory domain's business key."""
    assert InventoryDomainMixin.dedupe_key == "sku_id"
    assert DEDUPE_KEY == "sku_id"


def test_constructor_binds_the_given_source():
    """The source passed to __init__ is stored as self.source, unmodified."""
    source = _StubSource(pd.DataFrame())
    mixin = InventoryDomainMixin(source=source)
    assert mixin.source is source


def test_load_records_reads_from_the_bound_source_and_deduplicates():
    """load_records() calls source.read_records() and dedupes by dedupe_key."""
    raw = pd.DataFrame(
        [
            {"sku_id": "SKU-001", "item_name": "Widget", "unit_price": 9.99},
            {"sku_id": "SKU-001", "item_name": "Widget (updated)", "unit_price": 12.50},
            {"sku_id": "SKU-002", "item_name": "Gadget", "unit_price": 4.00},
        ]
    )
    mixin = InventoryDomainMixin(source=_StubSource(raw))

    records = mixin.load_records()

    assert len(records) == 2
    updated_row = records[records["sku_id"] == "SKU-001"].iloc[0]
    assert updated_row["item_name"] == "Widget (updated)"


def test_load_records_never_calls_read_records_more_than_once():
    """Each call to load_records() reads the source exactly once, not once per row processed."""

    class _CountingSource(_StubSource):
        def __init__(self, records: pd.DataFrame) -> None:
            super().__init__(records)
            self.read_count = 0

        def read_records(self) -> pd.DataFrame:
            self.read_count += 1
            return super().read_records()

    source = _CountingSource(pd.DataFrame([{"sku_id": "SKU-001", "item_name": "x", "unit_price": 1.0}]))
    mixin = InventoryDomainMixin(source=source)

    mixin.load_records()

    assert source.read_count == 1
