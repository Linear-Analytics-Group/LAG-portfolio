"""Unit tests for runners.dataverse.DataverseInventorySyncRunner.

Exercises only the constructor-injected configuration (dedupe_key,
entity_set, alternate_key_field, field_mapping) in isolation, with no
real source file and no HTTP mocking — the upsert loop itself is
covered by the acceptance-level idempotency tests. Proves a customer
deployment can adapt this leaf class's source- and destination-side
identifier names, and its field mapping, without forking any code (see
README.md's "Constructor Injection vs. Environment Bloat" and "Field
Mapping: Constructor-Injected Dict vs. External Mapping File").
"""

from types import SimpleNamespace

import pandas as pd
import pytest
from defaults import DEFAULT_MAX_WORKERS
from runners.base import DEDUPE_KEY
from runners.dataverse import (
    DEFAULT_ALTERNATE_KEY_FIELD,
    DEFAULT_ENTITY_SET,
    DEFAULT_FIELD_MAPPING,
    DataverseInventorySyncRunner,
)

pytestmark = pytest.mark.unit


class _StubSource:
    """A minimal InventorySource test double returning an empty DataFrame."""

    def read_records(self) -> pd.DataFrame:
        return pd.DataFrame()


class _FakeMsalApp:
    """A controllable stand-in for msal.ConfidentialClientApplication.

    Avoids the live OIDC tenant discovery network call
    ``msal.ConfidentialClientApplication`` performs at construction time.
    """

    def acquire_token_silent(  # type: ignore[no-untyped-def]
        self, scopes, account
    ):
        return None

    def acquire_token_for_client(  # type: ignore[no-untyped-def]
        self, scopes
    ):
        return {"access_token": "fake-bearer-token"}


class _StubSettings:
    """A minimal DataverseConnectionSettings test double."""

    azure_tenant_id = "stub-tenant-id"
    azure_client_id = "stub-client-id"
    azure_client_secret = "stub-client-secret"
    dataverse_url = "https://stub-org.crm.dynamics.com"


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


def test_build_payload_uses_the_default_field_mapping() -> None:
    """With no override, build_payload() matches today's shipped schema."""
    runner = DataverseInventorySyncRunner(source=_StubSource())
    row = SimpleNamespace(item_name="Widget", unit_price=9.99)

    assert runner.build_payload(row) == {
        "lagsol_name": "Widget",
        "lagsol_unitprice": 9.99,
    }
    assert DEFAULT_FIELD_MAPPING == {
        "item_name": "lagsol_name",
        "unit_price": "lagsol_unitprice",
    }


def test_build_payload_field_mapping_can_be_overridden() -> None:
    """A customer's differently-named source/destination fields override
    the default mapping — proving build_payload() is generic over the
    mapping's contents, not hardcoded to today's two fields.
    """
    runner = DataverseInventorySyncRunner(
        source=_StubSource(),
        field_mapping={"item_sku": "contoso_skucode", "qty": "contoso_qty"},
    )
    row = SimpleNamespace(item_sku="SKU-001", qty=42)

    assert runner.build_payload(row) == {
        "contoso_skucode": "SKU-001",
        "contoso_qty": 42,
    }


def test_build_client_pool_size_defaults_to_twice_max_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no override, the client's pool is 2x DEFAULT_MAX_WORKERS."""
    monkeypatch.setattr(
        "msal.ConfidentialClientApplication", lambda *a, **k: _FakeMsalApp()
    )
    runner = DataverseInventorySyncRunner(source=_StubSource())

    client = runner.build_client(_StubSettings())  # type: ignore[arg-type]

    adapter = client._session.get_adapter("https://stub-org.crm.dynamics.com")
    pool_maxsize = adapter._pool_maxsize  # type: ignore[attr-defined]
    assert pool_maxsize == DEFAULT_MAX_WORKERS * 2


def test_build_client_pool_size_tracks_a_custom_max_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raising max_workers grows the pool to 2x it, proving the two are

    actually wired together rather than each independently defaulting
    to numbers that happen to land in a 1:2 ratio by coincidence.
    """
    monkeypatch.setattr(
        "msal.ConfidentialClientApplication", lambda *a, **k: _FakeMsalApp()
    )
    runner = DataverseInventorySyncRunner(
        source=_StubSource(), max_workers=25
    )

    client = runner.build_client(_StubSettings())  # type: ignore[arg-type]

    adapter = client._session.get_adapter("https://stub-org.crm.dynamics.com")
    pool_maxsize = adapter._pool_maxsize  # type: ignore[attr-defined]
    assert pool_maxsize == 50
