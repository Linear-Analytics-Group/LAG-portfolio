"""Generic HTTP transport base shared by any HTTP-based connector."""

from typing import Tuple

import requests

from .base import BaseClient

#: (connect_timeout, read_timeout) in seconds. Connect should fail fast;
#: read allows for a destination's occasional slower responses under load.
DEFAULT_TIMEOUT: Tuple[float, float] = (5.0, 30.0)


class BaseHttpClient(BaseClient):
    """HTTP-transport base for any REST-ish connector (OData, plain REST, ...).

    Owns the parts of "being an HTTP client" that have nothing to do with
    any particular wire protocol built on top of HTTP: a pooled,
    keep-alive ``requests.Session`` and default request timeouts. Still
    abstract — ``acquire_bearer_token`` is unimplemented — so it cannot
    be instantiated directly; it exists only to be subclassed by a
    protocol-specific base like ``ODataClient``.
    """

    def __init__(self, timeout: Tuple[float, float] = DEFAULT_TIMEOUT) -> None:
        """Initialize the underlying HTTP session and default timeout.

        Parameters
        ----------
        timeout : Tuple[float, float]
            ``(connect_timeout, read_timeout)`` in seconds, applied to
            every HTTP request issued through this client's session.
            Defaults to :data:`DEFAULT_TIMEOUT`.

        Returns
        -------
        None
        """
        self._session: requests.Session = requests.Session()
        self._timeout: Tuple[float, float] = timeout
