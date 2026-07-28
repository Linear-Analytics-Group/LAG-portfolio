"""Integration: DataverseInventorySyncRunner's real settings/client wiring.

Unlike the acceptance tests, ``load_settings()`` and ``build_client()``
are *not* stubbed here — they run for real, proving
``InventorySyncSettings`` and ``DataverseClient.from_settings()`` really
do wire together end to end. Only the two true external boundaries are
mocked: MSAL's network-touching token acquisition, and the Dataverse
Web API's HTTP responses.
"""

import re
from typing import Any

import pytest
import responses
from runners.dataverse import DataverseInventorySyncRunner
from sources import CsvInventorySource

pytestmark = pytest.mark.integration

UPSERT_URL_PATTERN = re.compile(
    r".*/lagsol_inventoryitems\(lagsol_skuid='.*'\)$"
)

#: Syntactically valid but obviously fake GUIDs — real Entra ID
#: tenant/client IDs are always GUIDs, so DataverseConnectionSettings'
#: _validate_guid rejects plain placeholder strings now.
FAKE_TENANT_ID = "55555555-5555-5555-5555-555555555555"
FAKE_CLIENT_ID = "66666666-6666-6666-6666-666666666666"


class _FakeConfidentialClientApplication:
    """Stands in for ``msal.ConfidentialClientApplication``, no network I/O."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def acquire_token_silent(self, *args: object, **kwargs: object) -> None:
        return None

    def acquire_token_for_client(
        self, *args: object, **kwargs: object
    ) -> dict[str, Any]:
        return {"access_token": "fake-integration-test-token"}


@responses.activate
def test_run_wires_real_settings_and_client_to_the_configured_environment(
    monkeypatch: pytest.MonkeyPatch, csv_source: CsvInventorySource
) -> None:
    """The real load_settings()/build_client() target the configured URL."""
    monkeypatch.setenv("AZURE_TENANT_ID", FAKE_TENANT_ID)
    monkeypatch.setenv("AZURE_CLIENT_ID", FAKE_CLIENT_ID)
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("DATAVERSE_URL", "https://test-org.crm.dynamics.com")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(
        "msal.ConfidentialClientApplication",
        _FakeConfidentialClientApplication,
    )
    responses.add(responses.PATCH, UPSERT_URL_PATTERN, status=201)

    runner = DataverseInventorySyncRunner(source=csv_source)
    exit_code = runner.run()

    assert exit_code == 0
    assert len(responses.calls) == 3
    expected_prefix = (
        "https://test-org.crm.dynamics.com/api/data/v9.2/"
        "lagsol_inventoryitems"
    )
    assert all(
        (call.request.url or "").startswith(expected_prefix)
        for call in responses.calls
    )


@responses.activate
def test_run_sends_the_bearer_token_msal_actually_returns(
    monkeypatch: pytest.MonkeyPatch, csv_source: CsvInventorySource
) -> None:
    """The Authorization header carries the exact token the fake MSAL issued."""
    monkeypatch.setenv("AZURE_TENANT_ID", FAKE_TENANT_ID)
    monkeypatch.setenv("AZURE_CLIENT_ID", FAKE_CLIENT_ID)
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("DATAVERSE_URL", "https://test-org.crm.dynamics.com")
    monkeypatch.setattr(
        "msal.ConfidentialClientApplication",
        _FakeConfidentialClientApplication,
    )
    responses.add(responses.PATCH, UPSERT_URL_PATTERN, status=201)

    DataverseInventorySyncRunner(source=csv_source).run()

    assert all(
        call.request.headers["Authorization"]
        == "Bearer fake-integration-test-token"
        for call in responses.calls
    )
