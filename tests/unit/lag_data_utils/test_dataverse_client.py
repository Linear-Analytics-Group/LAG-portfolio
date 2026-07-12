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

pytestmark = pytest.mark.unit


class _FakeMsalApp:
    """A controllable stand-in for msal.ConfidentialClientApplication."""

    def __init__(self) -> None:
        self.silent_result: Optional[Dict[str, Any]] = None
        self.for_client_result: Optional[Dict[str, Any]] = None
        self.for_client_call_count = 0

    def acquire_token_silent(  # type: ignore[no-untyped-def]
        self, scopes, account
    ):
        return self.silent_result

    def acquire_token_for_client(  # type: ignore[no-untyped-def]
        self, scopes
    ):
        self.for_client_call_count += 1
        return self.for_client_result


@pytest.fixture
def fake_msal_app(monkeypatch: pytest.MonkeyPatch) -> _FakeMsalApp:
    """Patch msal.ConfidentialClientApplication with the controllable fake."""
    fake_app = _FakeMsalApp()
    monkeypatch.setattr(
        "msal.ConfidentialClientApplication", lambda *a, **k: fake_app
    )
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


def test_environment_url_trailing_slash_is_stripped(
    client: DataverseClient,
) -> None:
    """A trailing slash on environment_url never doubles up in base_url."""
    assert client.base_url == "https://fake-org.crm.dynamics.com/api/data/v9.2"


def test_acquire_bearer_token_returns_cached_token_without_fetching_a_new_one(
    client: DataverseClient, fake_msal_app: _FakeMsalApp
) -> None:
    """A cache hit (acquire_token_silent succeeds) never falls back."""
    fake_msal_app.silent_result = {"access_token": "cached-token"}

    token = client.acquire_bearer_token()

    assert token == "cached-token"
    assert fake_msal_app.for_client_call_count == 0


def test_acquire_bearer_token_fetches_fresh_token_on_cache_miss(
    client: DataverseClient, fake_msal_app: _FakeMsalApp
) -> None:
    """A cache miss falls back to a fresh client-credentials grant."""
    fake_msal_app.silent_result = None
    fake_msal_app.for_client_result = {"access_token": "fresh-token"}

    token = client.acquire_bearer_token()

    assert token == "fresh-token"
    assert fake_msal_app.for_client_call_count == 1


def test_acquire_bearer_token_raises_with_entra_error_description_on_rejection(
    client: DataverseClient, fake_msal_app: _FakeMsalApp
) -> None:
    """A rejected grant raises with Entra ID's error description."""
    fake_msal_app.silent_result = None
    fake_msal_app.for_client_result = {
        "error": "invalid_client",
        "error_description": "AADSTS7000215: Invalid client secret provided.",
    }

    with pytest.raises(DataverseAuthenticationError) as exc_info:
        client.acquire_bearer_token()

    assert "AADSTS7000215" in str(exc_info.value)


def test_acquire_bearer_token_raises_when_msal_returns_nothing(
    client: DataverseClient, fake_msal_app: _FakeMsalApp
) -> None:
    """No result at all from MSAL still raises with a sensible default."""
    fake_msal_app.silent_result = None
    fake_msal_app.for_client_result = None

    with pytest.raises(DataverseAuthenticationError) as exc_info:
        client.acquire_bearer_token()

    assert "No error description returned" in str(exc_info.value)


def test_get_headers_includes_prefer_return_representation(
    client: DataverseClient, fake_msal_app: _FakeMsalApp
) -> None:
    """Dataverse headers extend, rather than replace, the OData v4 ones."""
    fake_msal_app.silent_result = {"access_token": "cached-token"}

    headers = client._get_headers()

    assert headers["Prefer"] == "return=representation"
    assert headers["Authorization"] == "Bearer cached-token"
    assert headers["OData-Version"] == "4.0"


def test_from_settings_builds_a_client_from_any_matching_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """from_settings() accepts any object with the four required attrs."""
    monkeypatch.setattr(
        "msal.ConfidentialClientApplication", lambda *a, **k: _FakeMsalApp()
    )

    class _StubSettings:
        azure_tenant_id = "stub-tenant-id"
        azure_client_id = "stub-client-id"
        azure_client_secret = "stub-client-secret"
        dataverse_url = "https://stub-org.crm.dynamics.com"

    settings = _StubSettings()
    assert isinstance(settings, DataverseConnectionSettings)

    client = DataverseClient.from_settings(settings)

    assert client.base_url == "https://stub-org.crm.dynamics.com/api/data/v9.2"
