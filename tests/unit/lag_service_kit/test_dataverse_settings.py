"""Unit tests for lag_service_kit.dataverse_settings.

Covers DataverseConnectionSettings.
"""

import pytest
from lag_service_kit.dataverse_settings import DataverseConnectionSettings
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_valid_values_are_accepted(clean_env: pytest.MonkeyPatch) -> None:
    """All four required fields, when provided, are accepted as-is."""
    settings = DataverseConnectionSettings(
        azure_tenant_id="tenant-id",
        azure_client_id="client-id",
        azure_client_secret="client-secret",
        dataverse_url="https://org.crm.dynamics.com",
    )
    assert settings.azure_tenant_id == "tenant-id"
    assert settings.dataverse_url == "https://org.crm.dynamics.com"


def test_missing_required_fields_raise_validation_error(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """Every one of the four fields is required to avoid ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        DataverseConnectionSettings()

    missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
    assert missing_fields == {
        "azure_tenant_id",
        "azure_client_id",
        "azure_client_secret",
        "dataverse_url",
    }


def test_empty_string_fields_raise_validation_error(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """An empty string fails min_length=1, same as a missing field."""
    with pytest.raises(ValidationError):
        DataverseConnectionSettings(
            azure_tenant_id="",
            azure_client_id="client-id",
            azure_client_secret="client-secret",
            dataverse_url="https://org.crm.dynamics.com",
        )


def test_whitespace_is_stripped_from_all_four_fields(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """Leading/trailing whitespace is stripped before validation."""
    settings = DataverseConnectionSettings(
        azure_tenant_id="  tenant-id  ",
        azure_client_id="  client-id  ",
        azure_client_secret="  client-secret  ",
        dataverse_url="  https://org.crm.dynamics.com  ",
    )
    assert settings.azure_tenant_id == "tenant-id"
    assert settings.azure_client_id == "client-id"
    assert settings.azure_client_secret == "client-secret"
    assert settings.dataverse_url == "https://org.crm.dynamics.com"


def test_trailing_slash_is_stripped_from_dataverse_url(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """A trailing slash on dataverse_url never double-slashes downstream."""
    settings = DataverseConnectionSettings(
        azure_tenant_id="tenant-id",
        azure_client_id="client-id",
        azure_client_secret="client-secret",
        dataverse_url="https://org.crm.dynamics.com/",
    )
    assert settings.dataverse_url == "https://org.crm.dynamics.com"
