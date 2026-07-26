"""Pydantic settings mixin for services that connect to Microsoft Dataverse."""

import uuid
from typing import ClassVar
from urllib.parse import urlparse

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings


class DataverseConnectionSettings(BaseSettings):
    """Entra ID / Dataverse connection fields for a Dataverse-backed service.

    Parameters
    ----------
    azure_tenant_id : str
        Microsoft Entra ID tenant GUID for the target Dataverse environment.
        Read from the ``AZURE_TENANT_ID`` environment variable, or Azure
        Key Vault as ``azure-tenant-id`` when ``AZURE_KEY_VAULT_URL`` is
        set (see ``vault_secret_fields`` below).
    azure_client_id : str
        Application (client) ID of the registered Entra ID app. Read from
        the ``AZURE_CLIENT_ID`` environment variable, or Key Vault as
        ``azure-client-id``.
    azure_client_secret : str
        Client secret credential for the registered Entra ID application.
        Read from the ``AZURE_CLIENT_SECRET`` environment variable, or
        Key Vault as ``azure-client-secret``.
    dataverse_url : str
        Root URL of the target Dataverse environment (e.g.,
        ``"https://org.crm.dynamics.com"``). Read from the
        ``DATAVERSE_URL`` environment variable, or Key Vault as
        ``dataverse-url``. A trailing slash is stripped automatically.

    Notes
    -----
    All four fields are declared in ``vault_secret_fields``, not just
    ``azure_client_secret`` — the tenant ID, client ID, and Dataverse
    URL aren't credentials on their own, but together they identify
    exactly which Entra ID tenant and live Dataverse environment this
    points to. In a public repository, that's real reconnaissance
    value to an attacker (a specific target for phishing or
    consent-phishing against this exact app registration), even though
    none of the three would authenticate anything by themselves.

    Any concrete settings class mixing this in structurally satisfies
    ``lag_data_utils.clients.dataverse.DataverseConnectionSettings`` (a
    ``typing.Protocol``), and can be passed directly to
    ``DataverseClient.from_settings`` without ``lag_data_utils`` depending
    on Pydantic.
    """

    azure_tenant_id: str = Field(..., min_length=1)
    azure_client_id: str = Field(..., min_length=1)
    azure_client_secret: str = Field(..., min_length=1)
    dataverse_url: str = Field(..., min_length=1)

    vault_secret_fields: ClassVar[tuple[str, ...]] = (
        "azure_tenant_id",
        "azure_client_id",
        "azure_client_secret",
        "dataverse_url",
    )

    @field_validator(
        "azure_tenant_id",
        "azure_client_id",
        "azure_client_secret",
        "dataverse_url",
        mode="before",
    )
    @classmethod
    def _strip_whitespace(cls, value: str) -> str:
        """Strip leading/trailing whitespace from a raw environment value.

        Parameters
        ----------
        value : str
            The raw field value as read from the environment or `.env`
            file, prior to further validation.

        Returns
        -------
        str
            The value with leading and trailing whitespace removed.
        """
        return value.strip() if isinstance(value, str) else value

    @field_validator("dataverse_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        """Remove a trailing slash from the Dataverse environment URL.

        Parameters
        ----------
        value : str
            The whitespace-stripped Dataverse environment URL.

        Returns
        -------
        str
            The URL with any trailing ``/`` removed.
        """
        return value.rstrip("/")

    @field_validator("azure_tenant_id", "azure_client_id")
    @classmethod
    def _validate_guid(cls, value: str, info: ValidationInfo) -> str:
        """Confirm this Entra ID identifier is a syntactically real GUID.

        Parameters
        ----------
        value : str
            The whitespace-stripped field value.
        info : ValidationInfo
            Supplies ``info.field_name``, so this one function can
            name which of the two fields it's validating in its error
            message rather than reporting a generic complaint.

        Returns
        -------
        str
            ``value``, unchanged — a GUID has no canonical casing or
            formatting this validator needs to normalize.

        Raises
        ------
        ValueError
            If ``value`` isn't a syntactically valid GUID/UUID. Real
            Entra ID tenant and application IDs are always GUIDs; a
            typo'd or truncated value passes today's presence-only
            check silently and only surfaces later as an opaque
            MSAL/AADSTS authentication failure.
        """
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise ValueError(
                f"{info.field_name} must be a valid GUID (e.g. "
                f"'12345678-1234-1234-1234-123456789abc'), got "
                f"{value!r}."
            ) from exc
        return value

    @field_validator("dataverse_url")
    @classmethod
    def _validate_https_url(cls, value: str) -> str:
        """Confirm dataverse_url is an absolute https:// URL.

        Parameters
        ----------
        value : str
            The whitespace-stripped, trailing-slash-stripped URL.

        Returns
        -------
        str
            ``value``, unchanged.

        Raises
        ------
        ValueError
            If ``value`` has no ``https`` scheme or no host — e.g. a
            missing ``https://`` prefix, a plain ``http://`` URL, or a
            bare hostname. A malformed value passes today's
            presence-only check silently and only fails later, deep
            inside HTTP request construction or MSAL's authority
            setup, with a far less clear error.
        """
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(
                f"dataverse_url must be an absolute https:// URL "
                f"(e.g. 'https://org.crm.dynamics.com'), got {value!r}."
            )
        return value
