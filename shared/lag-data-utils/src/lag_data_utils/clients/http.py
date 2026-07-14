"""Generic HTTP transport base shared by any HTTP-based connector."""

from typing import Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base import BaseClient

#: (connect_timeout, read_timeout) in seconds. Connect should fail fast;
#: read allows for a destination's occasional slower responses under load.
DEFAULT_TIMEOUT: Tuple[float, float] = (5.0, 30.0)

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
        timeout: Tuple[float, float] = DEFAULT_TIMEOUT,
        retry: Retry = DEFAULT_RETRY,
    ) -> None:
        """Initialize the underlying HTTP session, timeout, and retry policy.

        Parameters
        ----------
        timeout : Tuple[float, float]
            ``(connect_timeout, read_timeout)`` in seconds, applied to
            every HTTP request issued through this client's session.
            Defaults to :data:`DEFAULT_TIMEOUT`.
        retry : Retry
            Retry policy mounted on this client's session for both
            ``http://`` and ``https://`` requests. Defaults to
            :data:`DEFAULT_RETRY`.

        Returns
        -------
        None
        """
        self._session: requests.Session = requests.Session()
        self._timeout: Tuple[float, float] = timeout
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
