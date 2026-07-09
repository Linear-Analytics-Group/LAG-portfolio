"""Runtime configuration for the ERP-to-Dataverse inventory sync engine.

Composes the shared ``lag_service_kit`` scaffolding — common service fields
(``log_level``) and the Dataverse connection fields any Dataverse-backed
service needs — adding nothing but this service's own ``.env`` location.
"""

from pathlib import Path

from lag_service_kit.dataverse_settings import DataverseConnectionSettings
from lag_service_kit.settings import BaseServiceSettings, find_repo_env_file
from pydantic_settings import SettingsConfigDict


class InventorySyncSettings(DataverseConnectionSettings, BaseServiceSettings):
    """Runtime configuration for the ERP-to-Dataverse inventory sync engine.

    Combines :class:`lag_service_kit.dataverse_settings.DataverseConnectionSettings`
    (``azure_tenant_id``, ``azure_client_id``, ``azure_client_secret``,
    ``dataverse_url``) with :class:`lag_service_kit.settings.BaseServiceSettings`
    (``log_level``). This service adds no fields of its own.

    Raises
    ------
    pydantic.ValidationError
        If any required field is unset or empty after reading process
        environment variables and the ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_file=find_repo_env_file(Path(__file__)),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
