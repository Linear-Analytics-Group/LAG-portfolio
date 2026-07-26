"""Abstract OData v4 protocol layer shared by all OData-compliant connectors."""

from abc import abstractmethod
from typing import Any, Optional, cast
from urllib.parse import quote

import requests
from lag_data_utils.clients.http import BaseHttpClient


class ODataClient(BaseHttpClient):
    """Abstract OData v4 client with standardized HTTP operations.

    ``ODataClient`` is the second layer of the connector hierarchy,
    sitting between the protocol-agnostic ``BaseClient`` and any
    concrete, system-specific connector implementation. It
    encapsulates the full set of HTTP operations defined by the
    OData v4 standard (OASIS OData Version 4.0, ISO/IEC 20802), making
    them available to any subclass without repetition.

    Because OData v4 strictly defines URL conventions, HTTP verb
    semantics, query option syntax (``$filter``, ``$select``,
    ``$top``, ``$skip``, ``$expand``), and JSON response envelope
    structure, all of these concerns can be implemented here once and
    reused across heterogeneous OData-compliant destinations —
    including Microsoft Dataverse, SAP S/4HANA Cloud, SharePoint
    Online, and others.

    Concrete subclasses are only required to supply two things:

    - A ``base_url`` property pointing to the root of their OData
      service endpoint.
    - An ``acquire_bearer_token`` implementation (inherited obligation
      from ``BaseClient``) that handles their specific identity
      provider.

    Subclasses may also override ``_get_headers`` to inject
    system-specific request headers (e.g.,
    ``Prefer: return=representation`` for Dataverse, or a CSRF token
    header for SAP OData v4 endpoints) while preserving the standard
    OData headers provided by this class.

    Parameters
    ----------
    None
        Construction (the pooled ``requests.Session`` and default
        request timeout) is inherited unchanged from
        :class:`~lag_data_utils.clients.http.BaseHttpClient`.

    Notes
    -----
    All write and delete operations call
    ``response.raise_for_status()`` before returning, surfacing HTTP
    4xx/5xx errors as ``requests.HTTPError`` at the call site. Query
    operations follow the same convention. Callers that need to
    inspect the raw response (e.g., to read a ``Retry-After`` header
    on a 429) should catch ``requests.HTTPError`` and access
    ``error.response``.

    The alternate-key URL pattern used by ``upsert_record``,
    ``get_record``, and ``delete_record`` follows the OData v4
    specification for string-valued alternate keys:
    ``/{entity_set}({key_name}='{key_value}')``. Numeric or GUID key
    values may require subclass overrides of ``_build_entity_url``.

    Examples
    --------
    Defining a concrete OData connector by subclassing ``ODataClient``:

    >>> class DataverseClient(ODataClient):
    ...     @property
    ...     def base_url(self) -> str:
    ...         return "https://org.crm.dynamics.com/api/data/v9.2"
    ...
    ...     def acquire_bearer_token(self) -> str:
    ...         # MSAL client-credentials flow against Microsoft Entra ID
    ...         ...
    """

    # ------------------------------------------------------------------
    # Abstract interface — must be implemented by concrete subclasses
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Root URL of the OData v4 service endpoint, without a trailing slash.

        Returns
        -------
        str
            The fully-qualified base URL for the target OData service
            (e.g., ``"https://org.crm.dynamics.com/api/data/v9.2"``).
        """
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Construct the standard OData v4 request headers for this connector.

        Acquires a fresh (or cached) Bearer token via
        ``acquire_bearer_token`` and combines it with the mandatory
        OData v4 protocol headers. Subclasses should call
        ``super()._get_headers()`` and extend the returned dictionary
        with any system-specific headers rather than replacing it
        entirely.

        Returns
        -------
        dict[str, str]
            A dictionary of HTTP request headers, including
            ``Authorization``, ``Content-Type``, ``OData-MaxVersion``,
            ``OData-Version``, and ``Accept``.
        """
        return {
            "Authorization": f"Bearer {self.acquire_bearer_token()}",
            "Content-Type": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Accept": "application/json",
        }

    @staticmethod
    def _encode_odata_string_value(value: str) -> str:
        """Escape and URL-encode a value for use inside an OData string literal.

        Two distinct, ordered transforms — conflating or reordering
        them produces a URL that is either broken or unsafe:

        1. **OData literal escaping.** Per the OData v4 ABNF
           (``SQUOTE-IN-STRING = SQUOTE SQUOTE``), a single quote
           *inside* a string value is escaped by doubling it, so the
           value can safely sit inside the surrounding ``'...'``
           delimiters this class adds around it. Skipping this step —
           the OData analogue of a SQL injection vulnerability, not
           merely a parsing accident — lets an embedded quote terminate
           the string literal early, and an attacker or a corrupted
           upstream record who controls this value could attempt to
           alter which record the resulting ``PATCH``/``GET``/``DELETE``
           actually targets, rather than just producing a malformed
           request. (This method only ever builds a single-key
           predicate, a narrower grammar than a ``$filter`` boolean
           expression — it does not, by itself, expose ``$filter``- or
           ``$expand``-style query-option injection; see
           ``query_records``'s ``odata_filter``/``select_fields``
           handling for that separate, currently-unused surface.)
        2. **URL percent-encoding.** Separately, the escaped value must
           be safe to sit inside a URL at all — spaces, ``#``, ``&``,
           ``/``, and non-ASCII characters all require percent-encoding
           or they corrupt the URL's own structure, independent of
           OData syntax. ``safe=""`` deliberately leaves nothing
           unencoded (the default ``safe="/"`` would let a value
           containing a literal ``/`` alter the URL's path structure).

        Parameters
        ----------
        value : str
            The raw, untrusted business-key value (e.g., a SKU sourced
            directly from an external feed).

        Returns
        -------
        str
            The value, quote-escaped then percent-encoded, safe to
            interpolate directly between the ``'...'`` delimiters of
            an OData string literal in a URL.
        """
        escaped = value.replace("'", "''")
        return quote(escaped, safe="")

    def _build_entity_url(
        self,
        entity_set: str,
        alternate_key_name: str,
        key_value: str,
    ) -> str:
        """Build the OData v4 alternate-key URL for a single entity resource.

        Constructs the canonical URL for addressing a specific record
        using an alternate key predicate, per the OData v4 URL
        convention: ``/{entity_set}({alternate_key_name}='{key_value}')``.

        Parameters
        ----------
        entity_set : str
            The pluralized logical name of the target entity collection.
        alternate_key_name : str
            The schema name of the alternate key field.
        key_value : str
            The string-valued business key identifying the target
            record. Untrusted, externally-sourced data — escaped and
            encoded via :meth:`_encode_odata_string_value` before being
            interpolated into the URL, never spliced in raw.

        Returns
        -------
        str
            The fully-qualified OData resource URL for the specified record.
        """
        encoded_value = self._encode_odata_string_value(key_value)
        entity_path = (
            f"{entity_set}({alternate_key_name}='{encoded_value}')"
        )
        return f"{self.base_url}/{entity_path}"

    # ------------------------------------------------------------------
    # OData v4 CRUD operations — standard across all compliant endpoints
    # ------------------------------------------------------------------

    def upsert_record(
        self,
        entity_set: str,
        alternate_key_name: str,
        key_value: str,
        payload: dict[str, Any],
    ) -> requests.Response:
        """Persist a record via an idempotent OData v4 upsert (HTTP PATCH).

        Issues an HTTP ``PATCH`` request against the alternate-key
        resource URL. The OData v4 specification guarantees upsert
        semantics: if a record with the specified alternate key value
        already exists it is updated in place; if no match is found, a
        new record is created. This makes the operation safe to retry
        in at-least-once delivery pipelines without risking duplicate
        record creation, provided the destination enforces uniqueness
        on ``alternate_key_name``.

        Parameters
        ----------
        entity_set : str
            The pluralized logical name of the target entity collection
            (e.g., ``"lagsol_inventoryitems"``).
        alternate_key_name : str
            The schema name of the unique alternate key field used to
            identify the record (e.g., ``"lagsol_ExternalSKUID"``).
        key_value : str
            The specific business key value targeting the record to
            upsert (e.g., an external SKU identifier or ERP primary key).
        payload : dict[str, Any]
            Field-value pairs to write to the destination record. Keys
            must be valid schema field names for ``entity_set``.

        Returns
        -------
        requests.Response
            The HTTP response from the OData service. A 204 (No Content)
            indicates a successful update; a 201 (Created) indicates a
            new record was inserted.

        Raises
        ------
        requests.HTTPError
            If the service returns a 4xx or 5xx status code.

        Examples
        --------
        >>> response = client.upsert_record(
        ...     entity_set="lagsol_inventoryitems",
        ...     alternate_key_name="lagsol_ExternalSKUID",
        ...     key_value="SKU-00421",
        ...     payload={
        ...         "lagsol_quantityonhand": 150,
        ...         "lagsol_unitcost": 12.99,
        ...     },
        ... )
        """
        url = self._build_entity_url(entity_set, alternate_key_name, key_value)
        headers = self._get_headers()
        response = self._session.patch(
            url, json=payload, headers=headers, timeout=self._timeout
        )
        response.raise_for_status()
        return response

    def get_record(
        self,
        entity_set: str,
        alternate_key_name: str,
        key_value: str,
        select_fields: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Retrieve a single record by its alternate key value.

        Issues an HTTP ``GET`` request for the entity resource
        addressed by the supplied alternate key predicate. An optional
        field projection can be applied via the OData ``$select``
        query option to limit the response payload to a subset of the
        entity's columns.

        Parameters
        ----------
        entity_set : str
            The pluralized logical name of the target entity collection.
        alternate_key_name : str
            The schema name of the alternate key field.
        key_value : str
            The business key value identifying the record to retrieve.
        select_fields : list[str], optional
            A list of field schema names to include in the response.
            If omitted, all fields are returned. Projecting only the
            required fields significantly reduces response payload
            size on wide entity types.

        Returns
        -------
        dict[str, Any]
            The deserialized JSON object representing the retrieved
            entity record.

        Raises
        ------
        requests.HTTPError
            If the record is not found (404) or the request is
            otherwise rejected by the service.

        Examples
        --------
        >>> record = client.get_record(
        ...     entity_set="lagsol_inventoryitems",
        ...     alternate_key_name="lagsol_ExternalSKUID",
        ...     key_value="SKU-00421",
        ...     select_fields=["lagsol_quantityonhand", "lagsol_unitcost"],
        ... )
        >>> print(record["lagsol_quantityonhand"])
        """
        url = self._build_entity_url(entity_set, alternate_key_name, key_value)
        params: dict[str, Any] = {}
        if select_fields:
            params["$select"] = ",".join(select_fields)
        headers = self._get_headers()
        response = self._session.get(
            url, params=params, headers=headers, timeout=self._timeout
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def query_records(
        self,
        entity_set: str,
        odata_filter: Optional[str] = None,
        select_fields: Optional[list[str]] = None,
        top: Optional[int] = None,
        skip: Optional[int] = None,
        order_by: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Query a collection of records using OData v4 system query options.

        Issues an HTTP ``GET`` request against the ``entity_set``
        collection endpoint, applying any supplied OData v4 query
        options as URL parameters. Returns the deserialized ``value``
        array from the OData JSON response envelope, abstracting the
        caller from the raw response structure.

        Parameters
        ----------
        entity_set : str
            The pluralized logical name of the target entity collection.
        odata_filter : str, optional
            An OData v4 ``$filter`` expression string to constrain the
            result set (e.g., ``"lagsol_quantityonhand lt 10"``).
        select_fields : list[str], optional
            A list of field schema names to include in each returned
            record. Equivalent to a SQL ``SELECT`` column list.
        top : int, optional
            Maximum number of records to return. Equivalent to SQL
            ``LIMIT``.
        skip : int, optional
            Number of records to skip before returning results. Used
            with ``top`` for pagination. Equivalent to SQL ``OFFSET``.
        order_by : str, optional
            An OData ``$orderby`` expression controlling result
            ordering (e.g., ``"lagsol_createdon desc"``).

        Returns
        -------
        list[dict[str, Any]]
            A list of deserialized entity record dictionaries. Returns
            an empty list if no records match the supplied filter
            expression.

        Raises
        ------
        requests.HTTPError
            If the service returns a 4xx or 5xx status code.

        Examples
        --------
        >>> low_stock = client.query_records(
        ...     entity_set="lagsol_inventoryitems",
        ...     odata_filter="lagsol_quantityonhand lt 10",
        ...     select_fields=[
        ...         "lagsol_ExternalSKUID",
        ...         "lagsol_quantityonhand",
        ...     ],
        ...     top=500,
        ...     order_by="lagsol_quantityonhand asc",
        ... )
        """
        url = f"{self.base_url}/{entity_set}"
        params: dict[str, Any] = {}
        if odata_filter:
            params["$filter"] = odata_filter
        if select_fields:
            params["$select"] = ",".join(select_fields)
        if top is not None:
            params["$top"] = top
        if skip is not None:
            params["$skip"] = skip
        if order_by:
            params["$orderby"] = order_by
        headers = self._get_headers()
        response = self._session.get(
            url, params=params, headers=headers, timeout=self._timeout
        )
        response.raise_for_status()
        return cast(list[dict[str, Any]], response.json().get("value", []))

    def delete_record(
        self,
        entity_set: str,
        alternate_key_name: str,
        key_value: str,
    ) -> requests.Response:
        """Delete a single record identified by its alternate key value.

        Issues an HTTP ``DELETE`` request against the alternate-key
        resource URL. A successful deletion returns HTTP 204 (No
        Content). Attempting to delete a record that does not exist
        will result in a 404 (Not Found) response, surfaced as a
        ``requests.HTTPError``.

        Parameters
        ----------
        entity_set : str
            The pluralized logical name of the target entity collection.
        alternate_key_name : str
            The schema name of the alternate key field.
        key_value : str
            The business key value identifying the record to delete.

        Returns
        -------
        requests.Response
            The HTTP response from the OData service. A 204 (No
            Content) indicates the record was successfully deleted.

        Raises
        ------
        requests.HTTPError
            If the record is not found (404) or the deletion is
            rejected (e.g., due to referential integrity constraints
            on the destination system).

        Examples
        --------
        >>> response = client.delete_record(
        ...     entity_set="lagsol_inventoryitems",
        ...     alternate_key_name="lagsol_ExternalSKUID",
        ...     key_value="SKU-00421",
        ... )
        """
        url = self._build_entity_url(entity_set, alternate_key_name, key_value)
        response = self._session.delete(
            url, headers=self._get_headers(), timeout=self._timeout
        )
        response.raise_for_status()
        return response
