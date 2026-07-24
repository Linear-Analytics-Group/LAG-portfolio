"""Unit tests for run_mock_sync's fake Entra ID/Dataverse layer.

Covers the individual pieces (_outcome_bucket, _FakeSession,
_build_mock_client) in isolation, so a failure here points precisely
at which piece of the demo's fakery broke — the acceptance-level test
(tests/acceptance/test_mock_sync_demo.py) covers the whole thing
running end to end.
"""

import pytest
import run_mock_sync
from lag_data_utils.clients.dataverse import DataverseClient

pytestmark = pytest.mark.unit

_SAMPLE_URL = (
    "https://mock-org.crm.dynamics.com/api/data/v9.2/"
    "lagsol_inventoryitems(lagsol_skuid='SKU-001')"
)


def test_outcome_bucket_is_deterministic() -> None:
    """The same URL always maps to the same bucket, not a random one."""
    first = run_mock_sync._outcome_bucket(_SAMPLE_URL, 100)
    second = run_mock_sync._outcome_bucket(_SAMPLE_URL, 100)

    assert first == second


def test_outcome_bucket_stays_within_the_requested_modulus() -> None:
    """The bucket is always a valid index for the given modulus."""
    bucket = run_mock_sync._outcome_bucket(_SAMPLE_URL, 100)

    assert 0 <= bucket < 100


def test_fake_session_patch_never_raises_building_the_response() -> None:
    """patch() always returns a Response, whatever bucket a URL lands in."""
    session = run_mock_sync._FakeSession()

    response = session.patch(_SAMPLE_URL, json={}, headers={}, timeout=(5, 30))

    assert response.status_code in {201, 204, 503}
    assert response.url == _SAMPLE_URL


def test_fake_session_patch_never_touches_the_real_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No real HTTP call is ever attempted — the base class is never used.

    Patches requests.Session.request (the method every real HTTP verb
    funnels through) to raise if called, then proves patch() still
    succeeds — confirming _FakeSession's override never delegates to
    the real network-touching implementation it inherits from.
    """
    import requests

    def _fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("a real network call should never be attempted")

    monkeypatch.setattr(requests.Session, "request", _fail_if_called)

    session = run_mock_sync._FakeSession()
    response = session.patch(_SAMPLE_URL)

    assert response.status_code in {201, 204, 503}


def test_build_mock_client_returns_a_real_dataverse_client() -> None:
    """The fake client is a real DataverseClient, not a duck-typed stand-in.

    This is what lets build_client()'s override type-check as a true
    Liskov-compatible override of DataverseInventorySyncRunner's real
    return type, with zero type: ignore anywhere.
    """
    client = run_mock_sync._build_mock_client()

    assert isinstance(client, DataverseClient)


def test_build_mock_client_acquires_a_token_with_no_network_call() -> None:
    """acquire_bearer_token() succeeds purely against the faked MSAL app."""
    client = run_mock_sync._build_mock_client()

    token = client.acquire_bearer_token()

    assert token == "mock-bearer-token"


def test_demo_runner_load_settings_needs_no_real_env_or_dotenv(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """load_settings() returns a usable stand-in with every real env var unset.

    clean_env clears every Dataverse/Azure/service environment
    variable — proving this override truly never reads any of them,
    unlike the real DataverseInventorySyncRunner.load_settings().
    """
    from sources import CsvInventorySource

    runner = run_mock_sync._DemoDataverseInventorySyncRunner(
        source=CsvInventorySource()
    )

    settings = runner.load_settings()

    assert settings.log_level == "INFO"
