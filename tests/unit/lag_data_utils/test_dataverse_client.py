"""Unit tests for lag_data_utils.clients.dataverse.DataverseClient.

Every test replaces ``msal.ConfidentialClientApplication`` before
constructing a client — the real class performs a live network call
(OIDC tenant discovery) at construction time, before any token is ever
requested.
"""

from typing import Any, Dict, Optional

import pytest
from lag_data_utils.clients.dataverse import (
    DataverseAuthenticationError,
    DataverseClient,
    DataverseConnectionSettings,
)


class _FakeMsalApp:
    """A controllable stand-in for msal.ConfidentialClientApplication."""

    def __init__(self) -> None:
        self.silent_result: Optional[Dict[str, Any]] = None
        self.for_client_result: Optional[Dict[str, Any]] = None
        self.for_client_call_count = 0

    def acquire_token_silent(self, scopes, account):  # type: ignore[no-untyped-def]
        return self.silent_result

    def acquire_token_for_client(self, scopes):  # type: ignore[no-untyped-def]
        self.for_client_call_count += 1
        return self.for_client_result


@pytest.fixture
def fake_msal_app(monkeypatch: pytest.MonkeyPatch) -> _FakeMsalApp:
    """Patch msal.ConfidentialClientApplication and return the controllable fake instance."""
    fake_app = _FakeMsalApp()
    monkeypatch.setattr("msal.ConfidentialClientApplication", lambda *a, **k: fake_app)
    return fake_app


@pytest.fixture
def client(fake_msal_app: _FakeMsalApp) -> DataverseClient:
    """A DataverseClient wired to the controllable fake MSAL app."""
    return DataverseClient(
        tenant_id="fake-tenant-id",
        client_id="fake-client-id",
        client_secret="fake-client-secret",
        environment_url="https://fake-org.crm.dynamics.com/",
    )


def test_environment_url_trailing_slash_is_stripped(client):
    """A trailing slash on environment_url is stripped, so base_url never has a double slash."""
    assert client.base_url == "https://fake-org.crm.dynamics.com/api/data/v9.2"


def test_acquire_bearer_token_returns_cached_token_without_fetching_a_new_one(client, fake_msal_app):
    """A cache hit (acquire_token_silent succeeds) is returned directly, never falling back."""
    fake_msal_app.silent_result = {"access_token": "cached-token"}

    token = client.acquire_bearer_token()

    assert token == "cached-token"
    assert fake_msal_app.for_client_call_count == 0


def test_acquire_bearer_token_fetches_fresh_token_on_cache_miss(client, fake_msal_app):
    """A cache miss (acquire_token_silent returns None) falls back to a fresh client-credentials grant."""
    fake_msal_app.silent_result = None
    fake_msal_app.for_client_result = {"access_token": "fresh-token"}

    token = client.acquire_bearer_token()

    assert token == "fresh-token"
    assert fake_msal_app.for_client_call_count == 1


def test_acquire_bearer_token_raises_with_entra_error_description_on_rejection(client, fake_msal_app):
    """A rejected grant raises DataverseAuthenticationError carrying Entra ID's error description."""
    fake_msal_app.silent_result = None
    fake_msal_app.for_client_result = {
        "error": "invalid_client",
        "error_description": "AADSTS7000215: Invalid client secret provided.",
    }

    with pytest.raises(DataverseAuthenticationError) as exc_info:
        client.acquire_bearer_token()

    assert "AADSTS7000215" in str(exc_info.value)


def test_acquire_bearer_token_raises_with_default_message_when_msal_returns_nothing(client, fake_msal_app):
    """No result at all from MSAL still raises cleanly, with a sensible default message."""
    fake_msal_app.silent_result = None
    fake_msal_app.for_client_result = None

    with pytest.raises(DataverseAuthenticationError) as exc_info:
        client.acquire_bearer_token()

    assert "No error description returned" in str(exc_info.value)


def test_get_headers_includes_prefer_return_representation(client, fake_msal_app):
    """Dataverse-specific headers extend, rather than replace, the standard OData v4 headers."""
    fake_msal_app.silent_result = {"access_token": "cached-token"}

    headers = client._get_headers()

    assert headers["Prefer"] == "return=representation"
    assert headers["Authorization"] == "Bearer cached-token"
    assert headers["OData-Version"] == "4.0"


def test_from_settings_builds_a_client_from_any_matching_object(monkeypatch: pytest.MonkeyPatch):
    """from_settings() accepts any object exposing the four required attributes — no import needed."""
    monkeypatch.setattr("msal.ConfidentialClientApplication", lambda *a, **k: _FakeMsalApp())

    class _StubSettings:
        azure_tenant_id = "stub-tenant-id"
        azure_client_id = "stub-client-id"
        azure_client_secret = "stub-client-secret"
        dataverse_url = "https://stub-org.crm.dynamics.com"

    settings = _StubSettings()
    assert isinstance(settings, DataverseConnectionSettings)

    client = DataverseClient.from_settings(settings)  # type: ignore[arg-type]

    assert client.base_url == "https://stub-org.crm.dynamics.com/api/data/v9.2"
