"""Unit tests for lag_data_utils.clients.http.BaseHttpClient."""

import pytest
import responses
from lag_data_utils.clients.http import (
    DEFAULT_POOL_CONNECTIONS,
    DEFAULT_POOL_MAXSIZE,
    DEFAULT_RETRY,
    DEFAULT_TIMEOUT,
    BaseHttpClient,
)
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

pytestmark = pytest.mark.unit

FAKE_URL = "https://fake.example.com/records"


class _ConcreteHttpClient(BaseHttpClient):
    """The minimum needed to instantiate ``BaseHttpClient`` for testing."""

    def acquire_bearer_token(self) -> str:
        return "fake-bearer-token"


def test_default_timeout_is_the_module_default() -> None:
    """A client built with no override uses DEFAULT_TIMEOUT."""
    client = _ConcreteHttpClient()
    assert client._timeout == DEFAULT_TIMEOUT


def test_custom_timeout_override_is_respected() -> None:
    """A client built with a custom timeout stores it, not the default."""
    client = _ConcreteHttpClient(timeout=(1.0, 2.0))
    assert client._timeout == (1.0, 2.0)


def test_default_pool_connections_is_independent_of_pool_maxsize() -> None:
    """pool_connections defaults to its own constant, not pool_maxsize.

    Guards against the two being conflated again: DEFAULT_POOL_MAXSIZE
    (20) and DEFAULT_POOL_CONNECTIONS (10) are deliberately different
    values, so a regression that re-derives one from the other would
    fail this assertion rather than passing by coincidence.
    """
    client = _ConcreteHttpClient()
    adapter = client._session.get_adapter("https://example.com")

    pool_connections = adapter._pool_connections  # type: ignore[attr-defined]
    assert pool_connections == DEFAULT_POOL_CONNECTIONS
    assert DEFAULT_POOL_CONNECTIONS != DEFAULT_POOL_MAXSIZE


def test_custom_pool_connections_does_not_affect_pool_maxsize() -> None:
    """Overriding pool_connections alone leaves pool_maxsize untouched."""
    client = _ConcreteHttpClient(pool_connections=3)
    adapter = client._session.get_adapter("https://example.com")

    pool_connections = adapter._pool_connections  # type: ignore[attr-defined]
    pool_maxsize = adapter._pool_maxsize  # type: ignore[attr-defined]
    assert pool_connections == 3
    assert pool_maxsize == DEFAULT_POOL_MAXSIZE


def test_custom_pool_maxsize_does_not_affect_pool_connections() -> None:
    """Overriding pool_maxsize alone leaves pool_connections untouched."""
    client = _ConcreteHttpClient(pool_maxsize=50)
    adapter = client._session.get_adapter("https://example.com")

    pool_maxsize = adapter._pool_maxsize  # type: ignore[attr-defined]
    pool_connections = adapter._pool_connections  # type: ignore[attr-defined]
    assert pool_maxsize == 50
    assert pool_connections == DEFAULT_POOL_CONNECTIONS


def test_default_retry_policy_is_mounted_on_both_schemes() -> None:
    """The default Retry policy is mounted for both http:// and https://."""
    client = _ConcreteHttpClient()

    for prefix in ("https://", "http://"):
        adapter = client._session.get_adapter(f"{prefix}example.com")
        assert isinstance(adapter, HTTPAdapter)
        assert adapter.max_retries is DEFAULT_RETRY


def test_default_retry_policy_covers_rate_limiting_and_server_errors() -> None:
    """The default policy retries 429/502/503/504 and honors Retry-After."""
    assert DEFAULT_RETRY.total == 3
    assert set(DEFAULT_RETRY.status_forcelist) == {429, 502, 503, 504}
    assert DEFAULT_RETRY.allowed_methods is not None
    assert "PATCH" in DEFAULT_RETRY.allowed_methods
    assert DEFAULT_RETRY.respect_retry_after_header is True


@responses.activate
def test_a_rate_limited_request_is_retried_until_it_succeeds() -> None:
    """A 429 followed by a 201 succeeds after one automatic retry."""
    fast_retry = Retry(
        total=2,
        backoff_factor=0.01,
        status_forcelist=[429],
        allowed_methods=frozenset(["PATCH"]),
    )
    client = _ConcreteHttpClient(retry=fast_retry)
    responses.add(responses.PATCH, FAKE_URL, status=429)
    responses.add(responses.PATCH, FAKE_URL, status=201)

    response = client._session.patch(FAKE_URL, timeout=client._timeout)

    assert response.status_code == 201
    assert len(responses.calls) == 2


@responses.activate
def test_a_plain_500_is_not_retried() -> None:
    """A 500 is not in the default forcelist, so it is not retried."""
    client = _ConcreteHttpClient()
    responses.add(responses.PATCH, FAKE_URL, status=500)

    response = client._session.patch(FAKE_URL, timeout=client._timeout)

    assert response.status_code == 500
    assert len(responses.calls) == 1
