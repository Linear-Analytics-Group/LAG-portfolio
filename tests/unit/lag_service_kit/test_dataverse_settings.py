"""Unit tests for lag_service_kit.dataverse_settings.DataverseConnectionSettings."""

import pytest
from lag_service_kit.dataverse_settings import DataverseConnectionSettings
from pydantic import ValidationError


def test_valid_values_are_accepted(clean_env):
    """All four required fields, when provided, are accepted as-is (aside from normalization)."""
    settings = DataverseConnectionSettings(
        azure_tenant_id="tenant-id",
        azure_client_id="client-id",
        azure_client_secret="client-secret",
        dataverse_url="https://org.crm.dynamics.com",
    )
    assert settings.azure_tenant_id == "tenant-id"
    assert settings.dataverse_url == "https://org.crm.dynamics.com"


def test_missing_required_fields_raise_validation_error(clean_env):
    """Every one of the four fields is required — omitting any raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        DataverseConnectionSettings()  # type: ignore[call-arg]

    missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
    assert missing_fields == {
        "azure_tenant_id",
        "azure_client_id",
        "azure_client_secret",
        "dataverse_url",
    }


def test_empty_string_fields_raise_validation_error(clean_env):
    """An empty string does not satisfy min_length=1 — it's treated the same as missing."""
    with pytest.raises(ValidationError):
        DataverseConnectionSettings(
            azure_tenant_id="",
            azure_client_id="client-id",
            azure_client_secret="client-secret",
            dataverse_url="https://org.crm.dynamics.com",
        )


def test_whitespace_is_stripped_from_all_four_fields(clean_env):
    """Leading/trailing whitespace from a raw environment value is stripped before validation."""
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


def test_trailing_slash_is_stripped_from_dataverse_url(clean_env):
    """A trailing slash on dataverse_url is removed so downstream URL-joining never double-slashes."""
    settings = DataverseConnectionSettings(
        azure_tenant_id="tenant-id",
        azure_client_id="client-id",
        azure_client_secret="client-secret",
        dataverse_url="https://org.crm.dynamics.com/",
    )
    assert settings.dataverse_url == "https://org.crm.dynamics.com"
