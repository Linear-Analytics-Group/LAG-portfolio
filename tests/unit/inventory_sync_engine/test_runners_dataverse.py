"""Unit tests for runners.dataverse.DataverseInventorySyncRunner.

Exercises only the constructor-injected configuration (dedupe_key,
entity_set, alternate_key_field) in isolation, with no real source
file and no HTTP mocking — the upsert loop itself is covered by the
acceptance-level idempotency tests. Proves a customer deployment can
adapt this leaf class's source- and destination-side identifier names
without forking any code (see README.md's "Constructor Injection vs.
Environment Bloat").
"""

import pandas as pd
import pytest
from runners.base import DEDUPE_KEY
from runners.dataverse import (
    DEFAULT_ALTERNATE_KEY_FIELD,
    DEFAULT_ENTITY_SET,
    DataverseInventorySyncRunner,
)

pytestmark = pytest.mark.unit


class _StubSource:
    """A minimal InventorySource test double returning an empty DataFrame."""

    def read_records(self) -> pd.DataFrame:
        return pd.DataFrame()


def test_defaults_match_the_shipped_dataverse_schema() -> None:
    """With no overrides, every value matches today's Dataverse schema."""
    runner = DataverseInventorySyncRunner(source=_StubSource())

    assert runner.dedupe_key == DEDUPE_KEY
    assert runner.entity_set == DEFAULT_ENTITY_SET
    assert runner.alternate_key_field == DEFAULT_ALTERNATE_KEY_FIELD


def test_dedupe_key_can_be_overridden() -> None:
    """A differently-named source record identifier overrides the default."""
    runner = DataverseInventorySyncRunner(
        source=_StubSource(), dedupe_key="item_sku"
    )

    assert runner.dedupe_key == "item_sku"


def test_entity_set_and_alternate_key_field_can_be_overridden() -> None:
    """A differently-shaped Dataverse schema overrides both defaults."""
    runner = DataverseInventorySyncRunner(
        source=_StubSource(),
        entity_set="contoso_items",
        alternate_key_field="contoso_itemcode",
    )

    assert runner.entity_set == "contoso_items"
    assert runner.alternate_key_field == "contoso_itemcode"
