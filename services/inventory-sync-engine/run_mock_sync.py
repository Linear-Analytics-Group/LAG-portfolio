"""Zero-setup demo entrypoint: the real sync engine, no Azure secrets needed.

Runs the real ``DataverseInventorySyncRunner``/``BaseSyncRunner``
orchestration against the shipped mock CSV feed, with a fake Entra
ID/Dataverse layer standing in for the two things this demo can't have
without a real Dataverse environment: MSAL token acquisition and the
destination's HTTP responses. Every other piece — dedup, the circuit
breaker, the JSON structured logging, the idempotent-upsert loop — is
the exact, unmodified production code path.

Run with::

    python3 run_mock_sync.py

No ``.env`` file, no Azure credentials, and no network access required.
"""

import hashlib
from typing import Any
from unittest.mock import patch

import requests
from lag_data_utils.clients.dataverse import DataverseClient
from runners.dataverse import DataverseInventorySyncRunner
from sources import CsvInventorySource

#: Obviously-fake, syntactically valid connection details — never a
#: real tenant, app registration, or Dataverse environment. Only need
#: to be well-formed enough to construct a real DataverseClient; no
#: network call is ever made against them (see
#: _FakeConfidentialClientApplication and _FakeSession below).
_MOCK_TENANT_ID = "00000000-0000-0000-0000-000000000000"
_MOCK_CLIENT_ID = "00000000-0000-0000-0000-000000000001"
_MOCK_CLIENT_SECRET = "mock-client-secret"
_MOCK_DATAVERSE_URL = "https://mock-org.crm.dynamics.com"


class _FakeConfidentialClientApplication:
    """Stands in for ``msal.ConfidentialClientApplication``, no network I/O.

    MSAL's real constructor performs a network call (OIDC tenant
    discovery) before any token is ever requested, so the class itself
    has to be replaced, not just a method — by the time an instance
    exists, construction has already tried to reach the network.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def acquire_token_silent(self, *args: Any, **kwargs: Any) -> None:
        return None

    def acquire_token_for_client(
        self, *args: Any, **kwargs: Any
    ) -> dict[str, str]:
        return {"access_token": "mock-bearer-token"}


def _outcome_bucket(url: str, modulus: int) -> int:
    """Deterministic pseudo-random bucket in ``[0, modulus)`` for a URL.

    Parameters
    ----------
    url : str
        The upsert request URL, which embeds the record's alternate
        key value.
    modulus : int
        The number of buckets to distribute across.

    Returns
    -------
    int
        A bucket index derived from an MD5 digest, not Python's own
        (randomized-per-process) ``hash()`` — so this demo's mixed
        created/updated/failed counts are identical on every run
        against the same mock feed, not something that looks flaky to
        someone re-running it.
    """
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()
    return int(digest, 16) % modulus


class _FakeSession(requests.Session):
    """A real ``requests.Session`` subclass that never touches the network.

    Subclassing the real class, rather than a hand-rolled stand-in,
    means ``DataverseClient``'s own ``_session: requests.Session``
    attribute stays honestly typed when this is swapped in — no
    ``type: ignore`` needed. Only ``.patch()`` is overridden: this demo
    only exercises the upsert loop, the one verb
    ``DataverseInventorySyncRunner.sync_records()`` actually calls.
    """

    def patch(self, *args: Any, **kwargs: Any) -> requests.Response:
        """Fabricate a response instead of issuing a real HTTP PATCH.

        Parameters
        ----------
        *args : Any
            Positional arguments a real call would pass; ``args[0]``
            is the target URL.
        **kwargs : Any
            Keyword arguments a real call would pass (``json``,
            ``headers``, ``timeout``); unused here.

        Returns
        -------
        requests.Response
            A response whose ``status_code`` is deterministically
            derived from the URL — about 38% ``201`` (created), 60%
            ``204`` (updated), and 2% ``503`` (a simulated transient
            failure). 2% of this feed's ~100 records is comfortably
            under the circuit breaker's default ``failure_threshold``
            of 5 *total* failures, so this demo can never trip it,
            regardless of dispatch order.
        """
        url = str(args[0]) if args else str(kwargs.get("url", ""))
        response = requests.Response()
        response.url = url
        bucket = _outcome_bucket(url, 100)
        if bucket < 2:
            response.status_code = 503
            response.reason = "Simulated Transient Failure (mock demo)"
        elif bucket < 40:
            response.status_code = 201
        else:
            response.status_code = 204
        response._content = b"{}"
        return response


def _build_mock_client() -> DataverseClient:
    """Build a real ``DataverseClient`` wired entirely to fakes.

    Returns
    -------
    DataverseClient
        A client that type-checks and behaves exactly like a real one
        to every caller, but never performs MSAL token acquisition or
        an HTTP request against a real network.
    """
    with patch(
        "msal.ConfidentialClientApplication",
        _FakeConfidentialClientApplication,
    ):
        client = DataverseClient(
            tenant_id=_MOCK_TENANT_ID,
            client_id=_MOCK_CLIENT_ID,
            client_secret=_MOCK_CLIENT_SECRET,
            environment_url=_MOCK_DATAVERSE_URL,
        )
    client._session = _FakeSession()
    return client


class _MockSettings:
    """Bare settings stand-in — only ``log_level`` is needed by ``run()``."""

    log_level: str = "INFO"


class _DemoDataverseInventorySyncRunner(DataverseInventorySyncRunner):
    """``DataverseInventorySyncRunner`` wired to fakes, not a real environment.

    Overrides exactly the two hooks that would otherwise require a
    real ``.env`` and a real Dataverse environment —
    :meth:`load_settings` and :meth:`build_client` — leaving every
    other method (``load_records()``, ``sync_records()``,
    ``build_payload()``, dedup, the circuit breaker) completely
    unmodified from the real, production leaf class.
    """

    def load_settings(self) -> Any:
        """Return a bare settings stand-in, skipping real .env/env-var reads.

        Returns
        -------
        Any
            A ``_MockSettings`` instance exposing only ``log_level``.
        """
        return _MockSettings()

    def build_client(self, settings: Any) -> DataverseClient:
        """Return a fully faked ``DataverseClient``, skipping real auth.

        Parameters
        ----------
        settings : Any
            Unused — the fake client's connection details are fixed.

        Returns
        -------
        DataverseClient
            A client wired entirely to :class:`_FakeSession` and
            :class:`_FakeConfidentialClientApplication`.
        """
        return _build_mock_client()


def main() -> int:
    """Run the full ERP-to-Dataverse inventory sync against fakes only.

    Returns
    -------
    int
        Process exit code: ``0`` if every simulated record synced
        without a simulated failure, ``1`` otherwise — identical exit
        code semantics to the real entrypoint, ``dataverse_sync_runner.py``.
    """
    return _DemoDataverseInventorySyncRunner(source=CsvInventorySource()).run()


if __name__ == "__main__":  # pragma: no cover — entrypoint, not import-time code
    raise SystemExit(main())
