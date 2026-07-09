"""Protocol-agnostic root of the Linear Analytics Group connector hierarchy."""

from abc import ABC, abstractmethod


class AuthenticationError(Exception):
    """Root of the connector authentication-failure hierarchy.

    Raised (via a system-specific subclass, e.g. ``DataverseAuthenticationError``)
    when a connector's identity provider rejects its credentials or its
    token response cannot be parsed or validated. Orchestration code that
    must remain agnostic to which destination system it is talking to
    (e.g. a sync runner) should catch this base class rather than any
    concrete subclass.
    """

    pass


class BaseClient(ABC):
    """Protocol-agnostic base class defining the minimum authentication contract for all connectors.

    ``BaseClient`` is the root of the Linear Analytics Group connector hierarchy.
    It establishes a single, universal obligation that every downstream integration
    adapter must fulfill: the ability to acquire a valid Bearer token from its
    identity provider before any data operations are attempted.

    The class is intentionally minimal. It makes no assumptions about the transport
    protocol (HTTP, gRPC, ODBC), the data format (JSON, XML, Parquet), or the
    persistence model (REST, SOAP, bulk load). Those concerns belong to
    protocol-specific subclasses further down the inheritance chain (e.g.,
    ``ODataClient``). By keeping this contract thin, new connector families can
    be introduced without inheriting unrelated interface requirements.

    Notes
    -----
    All concrete connector implementations must ultimately inherit from this class,
    either directly or through an intermediate abstract layer. Higher-level
    orchestration components (pipeline runners, sync engines, job schedulers)
    should program to this interface — or to a more specific descendant — rather
    than to any concrete connector type, preserving substitutability across
    destination systems.

    Examples
    --------
    Introducing a new connector family by subclassing ``BaseClient``:

    >>> # Abstract OData v4 connector with standardized HTTP operations.
    >>> class ODataClient(BaseClient):
    ...     @property
    ...     @abstractmethod
    ...     def base_url(self) -> str: ...
    ...
    ...     def acquire_bearer_token(self) -> str:
    ...         # Delegated to concrete subclasses (e.g., DataverseClient)
    ...         ...
    """

    @abstractmethod
    def acquire_bearer_token(self) -> str:
        """Acquire a valid OAuth 2.0 Bearer token from the destination system's identity provider.

        Executes the configured authentication flow — typically the OAuth 2.0
        Client Credentials grant — against the destination system's identity
        provider. Implementations are solely responsible for the full token
        lifecycle: sourcing credentials from secure storage, acquiring the
        initial token, serving cached tokens on repeat calls, and proactively
        refreshing tokens before they expire.

        Returns
        -------
        str
            A valid, non-expired OAuth 2.0 Bearer token string, suitable for
            direct use as the value of an ``Authorization: Bearer <token>``
            HTTP request header.

        Raises
        ------
        AuthenticationError
            Concrete subclasses should raise a system-specific subclass of
            ``AuthenticationError`` (e.g., ``DataverseAuthenticationError``)
            if the identity provider rejects the client credentials, the
            authority endpoint is unreachable, or the token response cannot
            be parsed or validated.

        Notes
        -----
        To avoid per-request authentication round-trips, implementations should
        leverage the token cache provided by the underlying authentication
        library (e.g., ``msal.ConfidentialClientApplication`` for Microsoft
        Entra ID) and only re-authenticate when the cached token is absent or
        within a short expiry window (typically 60–300 seconds).

        Examples
        --------
        >>> client = DataverseClient(
        ...     tenant_id="<tenant-id>",
        ...     client_id="<client-id>",
        ...     client_secret="<client-secret>",
        ...     environment_url="https://org.crm.dynamics.com",
        ... )
        >>> token = client.acquire_bearer_token()
        >>> headers = {"Authorization": f"Bearer {token}"}
        """
        pass
