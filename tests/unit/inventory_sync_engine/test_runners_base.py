"""Unit tests for runners.base.InventoryDomainMixin.

``InventoryDomainMixin`` does not inherit ``BaseSyncRunner`` and commits
to no client type, so it's instantiated directly here — no destination
leaf class is needed to test its dedup/source-binding behavior in
isolation.
"""

import pandas as pd
import pytest
from runners.base import DEDUPE_KEY, InventoryDomainMixin

pytestmark = pytest.mark.unit


class _StubSource:
    """A minimal InventorySource test double returning a fixed DataFrame."""

    def __init__(self, records: pd.DataFrame) -> None:
        self._records = records

    def read_records(self) -> pd.DataFrame:
        return self._records


def test_default_dedupe_key_is_sku_id() -> None:
    """With no override, dedupe_key matches the domain's business key."""
    mixin = InventoryDomainMixin(source=_StubSource(pd.DataFrame()))
    assert mixin.dedupe_key == "sku_id"
    assert DEDUPE_KEY == "sku_id"


def test_dedupe_key_override_is_stored() -> None:
    """A customer's differently-named business key overrides the default."""
    mixin = InventoryDomainMixin(
        source=_StubSource(pd.DataFrame()), dedupe_key="item_sku"
    )
    assert mixin.dedupe_key == "item_sku"


def test_constructor_binds_the_given_source() -> None:
    """The source passed to __init__ is stored as self.source, unmodified."""
    source = _StubSource(pd.DataFrame())
    mixin = InventoryDomainMixin(source=source)
    assert mixin.source is source


def test_load_records_reads_from_the_bound_source_and_deduplicates() -> None:
    """load_records() calls source.read_records() and dedupes by dedupe_key."""
    raw = pd.DataFrame(
        [
            {"sku_id": "SKU-001", "item_name": "Widget", "unit_price": 9.99},
            {
                "sku_id": "SKU-001",
                "item_name": "Widget (updated)",
                "unit_price": 12.50,
            },
            {"sku_id": "SKU-002", "item_name": "Gadget", "unit_price": 4.00},
        ]
    )
    mixin = InventoryDomainMixin(source=_StubSource(raw))

    records = mixin.load_records()

    assert len(records) == 2
    updated_row = records[records["sku_id"] == "SKU-001"].iloc[0]
    assert updated_row["item_name"] == "Widget (updated)"


def test_load_records_deduplicates_by_the_overridden_key() -> None:
    """Overriding dedupe_key changes which column load_records() uses."""
    raw = pd.DataFrame(
        [
            {"item_sku": "A", "item_name": "Widget", "unit_price": 1.0},
            {"item_sku": "A", "item_name": "Widget v2", "unit_price": 2.0},
        ]
    )
    mixin = InventoryDomainMixin(source=_StubSource(raw), dedupe_key="item_sku")

    records = mixin.load_records()

    assert len(records) == 1
    assert records.iloc[0]["item_name"] == "Widget v2"


def test_load_records_never_calls_read_records_more_than_once() -> None:
    """load_records() reads the source exactly once, not once per row."""

    class _CountingSource(_StubSource):
        def __init__(self, records: pd.DataFrame) -> None:
            super().__init__(records)
            self.read_count = 0

        def read_records(self) -> pd.DataFrame:
            self.read_count += 1
            return super().read_records()

    row = {"sku_id": "SKU-001", "item_name": "x", "unit_price": 1.0}
    source = _CountingSource(pd.DataFrame([row]))
    mixin = InventoryDomainMixin(source=source)

    mixin.load_records()

    assert source.read_count == 1


def test_constructor_cooperates_with_a_sibling_base_via_super() -> None:
    """__init__ calls super().__init__(), so it composes safely via MRO.

    A destination leaf class combines this mixin with a
    protocol-specific base via multiple inheritance (see
    ``runners.dataverse.DataverseInventorySyncRunner``). If this
    mixin's ``__init__`` didn't call ``super().__init__()``, any base
    it's mixed with that itself needs constructor-time state would
    have that state silently skipped, with no error. This proves the
    cooperative chain actually runs, using a stand-in protocol base
    that sets its own marker attribute.
    """

    class _StubProtocolBase:
        def __init__(self) -> None:
            super().__init__()
            self.protocol_base_initialized = True

    class _StubLeafRunner(InventoryDomainMixin, _StubProtocolBase):
        pass

    source = _StubSource(pd.DataFrame())
    runner = _StubLeafRunner(source=source)

    assert runner.source is source
    assert runner.protocol_base_initialized is True
