"""Unit tests for runners.base.InventoryDomainMixin.

``InventoryDomainMixin`` does not inherit ``BaseSyncRunner`` and commits
to no client type, so it's instantiated directly here — no destination
leaf class is needed to test its dedup/source-binding behavior in
isolation.
"""

from typing import Iterator, List

import pandas as pd
import pytest
from lag_service_kit.validation import RecordValidationError
from runners.base import DEDUPE_KEY, InventoryDomainMixin

pytestmark = pytest.mark.unit


class _StubSource:
    """A minimal InventorySource test double returning a fixed DataFrame."""

    def __init__(self, records: pd.DataFrame) -> None:
        self._records = records

    def read_records(self) -> pd.DataFrame:
        return self._records


class _StubChunkedSource:
    """A source satisfying both InventorySource and ChunkedInventorySource.

    Mirrors ``CsvInventorySource``'s real shape: every shipped chunked
    source also supports a plain full read, with chunking as an
    additional, optional capability layered on top — never a
    replacement for it. ``read_records`` deliberately raises rather
    than returning real data, so a test using this double proves
    ``load_records()`` took the chunked path via the fact that
    ``read_records`` was never called at all.
    """

    def __init__(self, chunks: List[pd.DataFrame]) -> None:
        self._chunks = chunks
        self.requested_chunksize: int = -1

    def read_records(self) -> pd.DataFrame:
        raise AssertionError(
            "read_records() should not be called for a chunked source"
        )

    def read_record_chunks(self, chunksize: int) -> Iterator[pd.DataFrame]:
        self.requested_chunksize = chunksize
        return iter(self._chunks)


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


def test_default_chunksize_is_stored() -> None:
    """With no override, chunksize matches the shipped default."""
    from defaults import DEFAULT_CHUNK_SIZE

    mixin = InventoryDomainMixin(source=_StubSource(pd.DataFrame()))
    assert mixin.chunksize == DEFAULT_CHUNK_SIZE


def test_chunksize_override_is_stored() -> None:
    """A customer-tuned chunk size overrides the default."""
    mixin = InventoryDomainMixin(
        source=_StubSource(pd.DataFrame()), chunksize=500
    )
    assert mixin.chunksize == 500


def test_load_records_uses_the_chunked_path_for_a_chunked_source() -> None:
    """A ChunkedInventorySource is read via read_record_chunks.

    Proves ``InventoryDomainMixin`` actually dispatches on the source's
    capability rather than always taking one fixed path — the stub
    source's ``read_records`` raises if called at all, so a passing
    test proves it was never reached.
    """
    chunk_one = pd.DataFrame(
        [{"sku_id": "SKU-001", "item_name": "Widget", "unit_price": 9.99}]
    )
    chunk_two = pd.DataFrame(
        [{"sku_id": "SKU-002", "item_name": "Gadget", "unit_price": 4.00}]
    )
    source = _StubChunkedSource([chunk_one, chunk_two])
    mixin = InventoryDomainMixin(source=source, chunksize=1)

    records = mixin.load_records()

    assert len(records) == 2
    assert source.requested_chunksize == 1


def test_load_records_deduplicates_across_a_chunk_boundary() -> None:
    """A duplicated key split across two chunks still resolves correctly.

    This is the property that would silently break memory-bounded
    reading if a naive implementation deduped each chunk independently
    instead of carrying last-seen state across the whole stream.
    """
    chunk_one = pd.DataFrame(
        [{"sku_id": "SKU-001", "item_name": "Widget", "unit_price": 9.99}]
    )
    chunk_two = pd.DataFrame(
        [
            {
                "sku_id": "SKU-001",
                "item_name": "Widget (updated)",
                "unit_price": 12.50,
            }
        ]
    )
    source = _StubChunkedSource([chunk_one, chunk_two])
    mixin = InventoryDomainMixin(source=source, chunksize=1)

    records = mixin.load_records()

    assert len(records) == 1
    assert records.iloc[0]["item_name"] == "Widget (updated)"


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


def test_default_required_columns_are_item_name_and_unit_price() -> None:
    """With no override, required_columns matches the shipped default."""
    from defaults import DEFAULT_REQUIRED_COLUMNS

    mixin = InventoryDomainMixin(source=_StubSource(pd.DataFrame()))
    assert mixin.required_columns == DEFAULT_REQUIRED_COLUMNS
    assert DEFAULT_REQUIRED_COLUMNS == ("item_name", "unit_price")


def test_load_records_raises_when_a_required_column_is_missing() -> None:
    """A feed missing unit_price fails clearly, before dedup runs."""
    raw = pd.DataFrame([{"sku_id": "SKU-001", "item_name": "Widget"}])
    mixin = InventoryDomainMixin(source=_StubSource(raw))

    with pytest.raises(RecordValidationError) as exc_info:
        mixin.load_records()

    assert "unit_price" in str(exc_info.value)


def test_load_records_raises_when_the_dedupe_key_is_missing_entirely() -> None:
    """A feed missing the business-key column itself is also caught."""
    raw = pd.DataFrame([{"item_name": "Widget", "unit_price": 9.99}])
    mixin = InventoryDomainMixin(source=_StubSource(raw))

    with pytest.raises(RecordValidationError) as exc_info:
        mixin.load_records()

    assert "sku_id" in str(exc_info.value)


def test_load_records_raises_when_the_dedupe_key_has_a_null_value() -> None:
    """A blank sku_id is rejected, since it can't identify a record."""
    raw = pd.DataFrame(
        [
            {"sku_id": "SKU-001", "item_name": "Widget", "unit_price": 9.99},
            {"sku_id": None, "item_name": "Gadget", "unit_price": 4.00},
        ]
    )
    mixin = InventoryDomainMixin(source=_StubSource(raw))

    with pytest.raises(RecordValidationError) as exc_info:
        mixin.load_records()

    assert "sku_id" in str(exc_info.value)
    assert "1 row" in str(exc_info.value)


def test_required_columns_override_changes_what_is_checked() -> None:
    """A customer's own schema can name different required columns."""
    raw = pd.DataFrame([{"sku_id": "SKU-001", "warehouse_code": "W1"}])
    mixin = InventoryDomainMixin(
        source=_StubSource(raw), required_columns=("warehouse_code",)
    )

    records = mixin.load_records()

    assert len(records) == 1


def test_load_records_raises_for_a_bad_chunk_before_reading_more() -> None:
    """A bad chunk fails validation before the next chunk is read.

    Proves validation runs per chunk, as each arrives, rather than
    only after every chunk has already been pulled from the source.
    """
    good_chunk = pd.DataFrame(
        [{"sku_id": "SKU-001", "item_name": "Widget", "unit_price": 9.99}]
    )
    bad_chunk = pd.DataFrame([{"sku_id": "SKU-002"}])

    class _StoppingChunkedSource(_StubChunkedSource):
        def read_record_chunks(
            self, chunksize: int
        ) -> Iterator[pd.DataFrame]:
            yield good_chunk
            yield bad_chunk
            raise AssertionError(
                "a chunk after the malformed one should never be read"
            )

    source = _StoppingChunkedSource([])
    mixin = InventoryDomainMixin(source=source, chunksize=1)

    with pytest.raises(RecordValidationError):
        mixin.load_records()
