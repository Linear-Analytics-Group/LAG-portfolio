"""Integration: DataverseInventorySyncRunner's real settings/client wiring.

Unlike the acceptance tests, ``load_settings()`` and ``build_client()``
are *not* stubbed here — they run for real, proving
``InventorySyncSettings`` and ``DataverseClient.from_settings()`` really
do wire together end to end. Only the two true external boundaries are
mocked: MSAL's network-touching token acquisition, and the Dataverse
Web API's HTTP responses.
"""

import re

import pytest
import responses
from runners.dataverse import DataverseInventorySyncRunner
from sources import CsvInventorySource

UPSERT_URL_PATTERN = re.compile(r".*/lagsol_inventoryitems\(lagsol_skuid='.*'\)$")


class _FakeConfidentialClientApplication:
    """Stands in for ``msal.ConfidentialClientApplication`` with no network I/O."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def acquire_token_silent(self, *args: object, **kwargs: object) -> None:
        return None

    def acquire_token_for_client(self, *args: object, **kwargs: object) -> dict:  # type: ignore[type-arg]
        return {"access_token": "fake-integration-test-token"}


@pytest.mark.integration
@responses.activate
def test_run_wires_real_settings_and_client_to_the_configured_environment(
    monkeypatch: pytest.MonkeyPatch, csv_source: CsvInventorySource
) -> None:
    """The runner's real load_settings()/build_client() point the client at the configured URL."""
    monkeypatch.setenv("AZURE_TENANT_ID", "test-tenant-id")
    monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("DATAVERSE_URL", "https://test-org.crm.dynamics.com")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setattr("msal.ConfidentialClientApplication", _FakeConfidentialClientApplication)
    responses.add(responses.PATCH, UPSERT_URL_PATTERN, status=201)

    runner = DataverseInventorySyncRunner(source=csv_source)
    exit_code = runner.run()

    assert exit_code == 0
    assert len(responses.calls) == 3
    assert all(
        (call.request.url or "").startswith(
            "https://test-org.crm.dynamics.com/api/data/v9.2/lagsol_inventoryitems"
        )
        for call in responses.calls
    )


@pytest.mark.integration
@responses.activate
def test_run_sends_the_bearer_token_msal_actually_returns(
    monkeypatch: pytest.MonkeyPatch, csv_source: CsvInventorySource
) -> None:
    """The Authorization header carries the exact token the (fake) MSAL app issued."""
    monkeypatch.setenv("AZURE_TENANT_ID", "test-tenant-id")
    monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("DATAVERSE_URL", "https://test-org.crm.dynamics.com")
    monkeypatch.setattr("msal.ConfidentialClientApplication", _FakeConfidentialClientApplication)
    responses.add(responses.PATCH, UPSERT_URL_PATTERN, status=201)

    DataverseInventorySyncRunner(source=csv_source).run()

    assert all(
        call.request.headers["Authorization"] == "Bearer fake-integration-test-token"
        for call in responses.calls
    )
