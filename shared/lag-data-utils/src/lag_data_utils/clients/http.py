"""Generic HTTP transport base shared by any HTTP-based connector."""

import requests
from lag_data_utils.clients.base import BaseClient
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

#: (connect_timeout, read_timeout) in seconds. Connect should fail fast;
#: read allows for a destination's occasional slower responses under load.
DEFAULT_TIMEOUT: tuple[float, float] = (5.0, 30.0)

#: Retry transient failures — rate limiting (429) and upstream server
#: hiccups (502/503/504) — with exponential backoff, honoring a
#: destination's Retry-After header when present. Safe to retry PATCH
#: and DELETE here specifically because every write in this codebase is
#: an idempotent alternate-key upsert (see CLAUDE.md Architectural
#: Directive 2) — a retried PATCH re-applies the same result rather
#: than creating a duplicate. A plain 500 is deliberately excluded:
#: it usually signals a destination-side error on this specific
#: record's data, not a transient condition retrying would resolve.
DEFAULT_RETRY: Retry = Retry(
    total=3,
    backoff_factor=1.0,
    status_forcelist=[429, 502, 503, 504],
    allowed_methods=frozenset(["GET", "PATCH", "DELETE"]),
    respect_retry_after_header=True,
)

#: Concurrent connections held open per host. Generous on its own
#: terms for any HTTP-based connector, independent of any particular
#: caller's concurrency setting — this package cannot know that a
#: service built on top uses, say, 10 worker threads (that would mean
#: this transport-layer package depending on an orchestration-layer
#: one, inverting the dependency direction this repo enforces). A
#: caller running more concurrent requests than this should pass a
#: larger ``pool_maxsize`` explicitly — see
#: ``DataverseInventorySyncRunner.build_client()`` for how this
#: service derives its client's pool size from its own concurrency
#: setting, rather than relying on this default to happen to match.
DEFAULT_POOL_MAXSIZE: int = 20

#: Distinct per-host connection pools to cache — an LRU keyed by host,
#: not a concurrency knob. Unrelated to ``DEFAULT_POOL_MAXSIZE``: every
#: client in this codebase talks to exactly one host per instance (see
#: ``DataverseClient``'s single ``environment_url``), so this never
#: needs to scale with worker count — it stays at requests' own
#: long-standing default regardless of how large ``pool_maxsize`` gets.
#: Set in place here to support multi-host future implementations
DEFAULT_POOL_CONNECTIONS: int = 10


class BaseHttpClient(BaseClient):
    """HTTP-transport base for any REST-ish connector (OData, plain REST, ...).

    Owns the parts of "being an HTTP client" that have nothing to do with
    any particular wire protocol built on top of HTTP: a pooled,
    keep-alive ``requests.Session``, default request timeouts, and
    automatic retry-with-backoff for transient failures. Still
    abstract — ``acquire_bearer_token`` is unimplemented — so it cannot
    be instantiated directly; it exists only to be subclassed by a
    protocol-specific base like ``ODataClient``.
    """

    def __init__(
        self,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        retry: Retry = DEFAULT_RETRY,
        pool_maxsize: int = DEFAULT_POOL_MAXSIZE,
        pool_connections: int = DEFAULT_POOL_CONNECTIONS,
    ) -> None:
        """Initialize the underlying HTTP session, timeout, and retry policy.

        Parameters
        ----------
        timeout : tuple[float, float]
            ``(connect_timeout, read_timeout)`` in seconds, applied to
            every HTTP request issued through this client's session.
            Defaults to :data:`DEFAULT_TIMEOUT`.
        retry : Retry
            Retry policy mounted on this client's session for both
            ``http://`` and ``https://`` requests. Defaults to
            :data:`DEFAULT_RETRY`.
        pool_maxsize : int
            Concurrent connections held open per host. If a caller
            issues more concurrent requests than this against one
            client instance, the excess simply queue for a free pooled
            connection — silently capping effective concurrency below
            whatever the caller configured, with no error raised.
            Defaults to :data:`DEFAULT_POOL_MAXSIZE`.
        pool_connections : int
            Distinct per-host connection pools to cache — an LRU keyed
            by host, unrelated to ``pool_maxsize``. Defaults to
            :data:`DEFAULT_POOL_CONNECTIONS`.

        Returns
        -------
        None
        """
        self._session: requests.Session = requests.Session()
        self._timeout: tuple[float, float] = timeout
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_maxsize=pool_maxsize,
            pool_connections=pool_connections,
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
