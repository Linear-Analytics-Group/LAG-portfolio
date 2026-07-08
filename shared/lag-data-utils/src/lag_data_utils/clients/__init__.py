"""Connector hierarchy for the Linear Analytics Group data platform.

This package exposes a layered set of client abstractions and concrete
connector implementations for writing data to external destination systems.

Hierarchy
---------
BaseClient
    Protocol-agnostic root. Enforces the authentication contract
    (``acquire_bearer_token``) across all connector families.

ODataClient(BaseClient)
    Abstract OData v4 adapter. Provides concrete, standard-compliant
    HTTP operations (upsert, get, query, delete) reusable across any
    OData v4-compliant destination (Dataverse, SAP S/4HANA, etc.).

DataverseClient(ODataClient)
    Fully-realized connector for Microsoft Dataverse / Power Platform.
    Implements MSAL-based Entra ID authentication and the Dataverse
    Web API v9.2 endpoint. Ready to instantiate — no subclassing required.

Note
----
``BaseClient`` and ``ODataClient`` are abstract and cannot be instantiated
directly (each declares abstractmethods); use them only for type
annotations or as a base to subclass from. Only ``DataverseClient`` (or
another concrete leaf connector) may be instantiated.

Usage
-----
For most use cases, import and instantiate ``DataverseClient`` directly:

>>> from lag_data_utils.clients import DataverseClient
>>> client = DataverseClient(
...     tenant_id="<tenant-id>",
...     client_id="<client-id>",
...     client_secret="<client-secret>",
...     environment_url="https://org.crm.dynamics.com",
... )

To build a new OData v4 connector (e.g., for SAP S/4HANA), subclass
``ODataClient`` and implement ``acquire_bearer_token`` and ``base_url``:

>>> from lag_data_utils.clients import ODataClient
>>> class SAPClient(ODataClient): ...

For broad dependency injection or type annotations that span all connector
families, use ``BaseClient``:

>>> from lag_data_utils.clients import BaseClient
>>> def run_sync(client: BaseClient) -> None: ...
"""

from .base import BaseClient
from .odata import ODataClient
from .dataverse import DataverseClient, DataverseAuthenticationError

__all__ = [
    "BaseClient",
    "ODataClient",
    "DataverseClient",
    "DataverseAuthenticationError",
]
