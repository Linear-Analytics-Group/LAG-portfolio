"""Concrete Microsoft Dataverse OData v4 connector implementation."""

import threading
from typing import (
    Any,
    Protocol,
    cast,
    runtime_checkable,
)

import msal
from urllib3.util.retry import Retry

from lag_data_utils.clients.base import AuthenticationError
from lag_data_utils.clients.http import (
    DEFAULT_POOL_CONNECTIONS,
    DEFAULT_POOL_MAXSIZE,
    DEFAULT_RETRY,
    DEFAULT_TIMEOUT,
)
from lag_data_utils.clients.odata import ODataClient


@runtime_checkable
class DataverseConnectionSettings(Protocol):
    """Structural contract for objects that can construct a ``DataverseClient``.

    Any object exposing these four string attributes — for example a
    Pydantic settings model from ``lag_service_kit`` — satisfies this
    protocol and can be passed to ``DataverseClient.from_settings``.
    ``lag_data_utils`` deliberately depends on no particular configuration
    framework; this protocol describes only the shape it needs.
    """

    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str
    dataverse_url: str


class DataverseAuthenticationError(AuthenticationError):
    """Raised when the Microsoft Entra ID token acquisition flow fails.

    Wraps the error description returned by the MSAL library to provide
    actionable context without exposing raw MSAL response dictionaries to
    callers. Subclasses ``lag_data_utils.clients.base.AuthenticationError``
    so destination-agnostic orchestration code can catch authentication
    failures without importing this Dataverse-specific type.
    """

    pass


class DataverseClient(ODataClient):
    """Concrete OData v4 connector for Microsoft Dataverse (Power Platform).

    ``DataverseClient`` is the fully-realized integration adapter for
    Microsoft Dataverse environments. It fulfills the two abstract contracts
    established by its ancestors:

    - ``acquire_bearer_token`` (from ``BaseClient``) — implemented via the
      OAuth 2.0 Client Credentials grant against Microsoft Entra ID, using
      the MSAL ``ConfidentialClientApplication`` with built-in token caching.
    - ``base_url`` (from ``ODataClient``) — derived from the Dataverse
      environment URL, targeting the Web API v9.2 OData endpoint.

    In addition, this class overrides ``_get_headers`` to inject the
    ``Prefer: return=representation`` header, which instructs the Dataverse
    Web API to return the full record body on successful upsert and create
    operations (rather than the default empty 204 response).

    All standard CRUD and query operations defined by ``ODataClient`` —
    ``upsert_record``, ``get_record``, ``query_records``, ``delete_record``
    — are available on this class without further implementation.

    Parameters
    ----------
    tenant_id : str
        The Microsoft Entra ID tenant GUID for the target Dataverse environment.
    client_id : str
        The application (client) ID of the registered Entra ID app with
        Dataverse API permissions.
    client_secret : str
        The client secret credential for the registered Entra ID application.
        Should be sourced from a secrets manager (e.g., Azure Key Vault) at
        runtime rather than hardcoded.
    environment_url : str
        The root URL of the target Dataverse environment
        (e.g., ``"https://org.crm.dynamics.com"``). A trailing slash is
        stripped automatically.

    Notes
    -----
    The MSAL ``ConfidentialClientApplication`` is instantiated once at
    initialization and reused for all subsequent ``acquire_bearer_token`` calls.
    Tokens are served from MSAL's in-memory cache, and a fresh token is only
    fetched from Entra ID when the cached token is absent or expired. This
    approach avoids redundant network round-trips on high-throughput pipelines.

    The Dataverse Web API endpoint is pinned to ``/api/data/v9.2``. If a
    future migration targets a different API version, override the ``base_url``
    property in a subclass rather than modifying this class.

    Examples
    --------
    >>> from lag_data_utils.clients.dataverse import DataverseClient
    >>>
    >>> client = DataverseClient(
    ...     tenant_id="<entra-tenant-id>",
    ...     client_id="<app-client-id>",
    ...     client_secret="<app-client-secret>",
    ...     environment_url="https://org.crm.dynamics.com",
    ... )
    >>>
    >>> # Upsert an inventory record
    >>> client.upsert_record(
    ...     entity_set="lagsol_inventoryitems",
    ...     alternate_key_name="lagsol_ExternalSKUID",
    ...     key_value="SKU-00421",
    ...     payload={"lagsol_quantityonhand": 150, "lagsol_unitcost": 12.99},
    ... )
    >>>
    >>> # Query low-stock items
    >>> low_stock = client.query_records(
    ...     entity_set="lagsol_inventoryitems",
    ...     odata_filter="lagsol_quantityonhand lt 10",
    ...     select_fields=["lagsol_ExternalSKUID", "lagsol_quantityonhand"],
    ... )
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        environment_url: str,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        retry: Retry = DEFAULT_RETRY,
        pool_maxsize: int = DEFAULT_POOL_MAXSIZE,
        pool_connections: int = DEFAULT_POOL_CONNECTIONS,
    ) -> None:
        """Initialize the Dataverse connector and its MSAL confidential client.

        Parameters
        ----------
        tenant_id : str
            The Microsoft Entra ID tenant GUID for the target Dataverse
            environment.
        client_id : str
            The application (client) ID of the registered Entra ID app with
            Dataverse API permissions.
        client_secret : str
            The client secret credential for the registered Entra ID
            application.
        environment_url : str
            The root URL of the target Dataverse environment. A trailing
            slash is stripped automatically.
        timeout : tuple[float, float]
            ``(connect_timeout, read_timeout)`` in seconds for every
            request this client issues. Defaults to
            :data:`~lag_data_utils.clients.http.DEFAULT_TIMEOUT`.
        retry : Retry
            Retry policy for transient failures on every request this
            client issues. Defaults to
            :data:`~lag_data_utils.clients.http.DEFAULT_RETRY`.
        pool_maxsize : int
            Concurrent connections held open for this client. A caller
            issuing more concurrent requests than this against one
            client instance silently caps its own concurrency at this
            number. Defaults to
            :data:`~lag_data_utils.clients.http.DEFAULT_POOL_MAXSIZE`.
        pool_connections : int
            Distinct per-host connection pools cached by this client.
            Unrelated to ``pool_maxsize``: this environment is always a
            single host, so it never needs to scale with concurrency.
            Defaults to
            :data:`~lag_data_utils.clients.http.DEFAULT_POOL_CONNECTIONS`.

        Returns
        -------
        None
        """
        super().__init__(
            timeout=timeout,
            retry=retry,
            pool_maxsize=pool_maxsize,
            pool_connections=pool_connections,
        )
        self._environment_url: str = environment_url.rstrip("/")
        self._msal_app: msal.ConfidentialClientApplication = (
            msal.ConfidentialClientApplication(
                client_id=client_id,
                client_credential=client_secret,
                authority=f"https://login.microsoftonline.com/{tenant_id}",
            )
        )
        self._scope: list[str] = [f"{self._environment_url}/.default"]
        self._token_lock: threading.Lock = threading.Lock()

    # ------------------------------------------------------------------
    # Alternate constructor
    # ------------------------------------------------------------------

    @classmethod
    def from_settings(
        cls,
        settings: DataverseConnectionSettings,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        retry: Retry = DEFAULT_RETRY,
        pool_maxsize: int = DEFAULT_POOL_MAXSIZE,
        pool_connections: int = DEFAULT_POOL_CONNECTIONS,
    ) -> "DataverseClient":
        """Construct a ``DataverseClient`` from a settings-like object.

        Parameters
        ----------
        settings : DataverseConnectionSettings
            Any object exposing ``azure_tenant_id``, ``azure_client_id``,
            ``azure_client_secret``, and ``dataverse_url`` attributes (e.g.,
            a ``lag_service_kit.dataverse_settings.DataverseConnectionSettings``
            instance). This client has no dependency on whatever
            configuration framework produced ``settings``.
        timeout : tuple[float, float]
            Forwarded to :meth:`__init__`. Defaults to
            :data:`~lag_data_utils.clients.http.DEFAULT_TIMEOUT`.
        retry : Retry
            Forwarded to :meth:`__init__`. Defaults to
            :data:`~lag_data_utils.clients.http.DEFAULT_RETRY`.
        pool_maxsize : int
            Forwarded to :meth:`__init__`. Defaults to
            :data:`~lag_data_utils.clients.http.DEFAULT_POOL_MAXSIZE`.
        pool_connections : int
            Forwarded to :meth:`__init__`. Defaults to
            :data:`~lag_data_utils.clients.http.DEFAULT_POOL_CONNECTIONS`.

        Returns
        -------
        DataverseClient
            A client authenticated against the Dataverse environment
            identified by ``settings.dataverse_url``.

        Notes
        -----
        Earlier versions of this method silently ignored any
        ``timeout``/``retry`` override, since it never accepted or
        forwarded them at all — meaning a caller could override these
        on :meth:`__init__` directly, but never through this alternate
        constructor, which is the one production actually uses (see
        ``DataverseInventorySyncRunner.build_client()``). Fixed here so
        overrides reach the client regardless of which constructor
        built it.
        """
        return cls(
            tenant_id=settings.azure_tenant_id,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
            environment_url=settings.dataverse_url,
            timeout=timeout,
            retry=retry,
            pool_maxsize=pool_maxsize,
            pool_connections=pool_connections,
        )

    # ------------------------------------------------------------------
    # BaseClient contract
    # ------------------------------------------------------------------

    def acquire_bearer_token(self) -> str:
        """Acquire an OAuth 2.0 Bearer token from Microsoft Entra ID.

        Attempts to serve a valid token from MSAL's in-memory cache first.
        If no valid cached token is available, executes the OAuth 2.0 Client
        Credentials grant to obtain a fresh token from Entra ID. The newly
        acquired token is stored in the MSAL cache automatically for reuse
        on subsequent calls within the token's validity window.

        Returns
        -------
        str
            A valid, non-expired Bearer token scoped to the Dataverse
            environment's default API scope (``{environment_url}/.default``).

        Raises
        ------
        DataverseAuthenticationError
            If the Entra ID token endpoint rejects the client credentials,
            the authority URL is unreachable, or the MSAL response does not
            contain a valid ``access_token``.

        Notes
        -----
        MSAL handles token refresh automatically. The ``acquire_token_silent``
        call returns a cached token if its remaining lifetime exceeds MSAL's
        internal refresh threshold (approximately 5 minutes before expiry),
        eliminating unnecessary authentication network traffic.

        Double-checked locking guards the network round-trip, not the
        cache lookup: this method is called from every worker thread in
        a concurrent sync run (see
        ``lag_service_kit.runners.odata.BaseODataSyncRunner.sync_records``)
        to prevent cases wherein every thread that happens to see the
        cache expire at the same moment would independently fire its own
        ``acquire_token_for_client`` call against Entra ID. The initial
        unlocked ``acquire_token_silent`` call keeps the common
        cache-hit path lock-free. Only a miss acquires
        :attr:`_token_lock`, and immediately re-checks the cache before
        refreshing — so of however many threads see the initial miss,
        only the first to acquire the lock actually calls Entra ID; every
        thread behind it in the queue sees the now-populated cache on
        its second check and never issues a redundant request.
        """
        result: dict[str, Any] | None = self._msal_app.acquire_token_silent(
            scopes=self._scope, account=None
        )
        if not result:
            with self._token_lock:
                result = self._msal_app.acquire_token_silent(
                    scopes=self._scope, account=None
                )
                if not result:
                    result = self._msal_app.acquire_token_for_client(
                        scopes=self._scope
                    )

        if not result or "access_token" not in result:
            error_description: str = (result or {}).get(
                "error_description",
                "No error description returned by Microsoft Entra ID.",
            )
            raise DataverseAuthenticationError(
                "Failed to acquire Bearer token from Microsoft Entra ID: "
                f"{error_description}"
            )

        return cast(str, result["access_token"])

    # ------------------------------------------------------------------
    # ODataClient contract
    # ------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        """Root URL of the Dataverse Web API OData v4 endpoint.

        Returns
        -------
        str
            The fully-qualified Dataverse Web API base URL, targeting the
            v9.2 API version (e.g.,
            ``"https://org.crm.dynamics.com/api/data/v9.2"``).
        """
        return f"{self._environment_url}/api/data/v9.2"

    # ------------------------------------------------------------------
    # Dataverse-specific header overrides
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Construct Dataverse-specific HTTP request headers.

        Extends the standard OData v4 headers provided by ``ODataClient``
        with the ``Prefer: return=representation`` directive. This instructs
        the Dataverse Web API to return the full record body in the response
        to successful upsert and create operations, enabling callers to
        inspect the server-assigned field values (e.g., system-generated
        GUIDs, audit timestamps) without a subsequent ``GET`` request.

        Returns
        -------
        dict[str, str]
            A dictionary of HTTP request headers combining the standard OData
            v4 headers with the Dataverse-specific ``Prefer`` header.
        """
        headers = super()._get_headers()
        headers["Prefer"] = "return=representation"
        return headers
