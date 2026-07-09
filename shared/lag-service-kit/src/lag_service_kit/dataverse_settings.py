"""Pydantic settings mixin for services that connect to Microsoft Dataverse."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class DataverseConnectionSettings(BaseSettings):
    """Entra ID / Dataverse connection fields shared by every Dataverse-backed service.

    Parameters
    ----------
    azure_tenant_id : str
        Microsoft Entra ID tenant GUID for the target Dataverse environment.
        Read from the ``AZURE_TENANT_ID`` environment variable.
    azure_client_id : str
        Application (client) ID of the registered Entra ID app. Read from
        the ``AZURE_CLIENT_ID`` environment variable.
    azure_client_secret : str
        Client secret credential for the registered Entra ID application.
        Read from the ``AZURE_CLIENT_SECRET`` environment variable.
    dataverse_url : str
        Root URL of the target Dataverse environment (e.g.,
        ``"https://org.crm.dynamics.com"``). Read from the
        ``DATAVERSE_URL`` environment variable. A trailing slash is
        stripped automatically.

    Notes
    -----
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
