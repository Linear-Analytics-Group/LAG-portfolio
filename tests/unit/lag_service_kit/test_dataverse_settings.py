"""Unit tests for lag_service_kit.dataverse_settings.

Covers DataverseConnectionSettings.
"""

import pytest
from lag_service_kit.dataverse_settings import DataverseConnectionSettings
from pydantic import ValidationError

pytestmark = pytest.mark.unit

#: Syntactically valid but obviously fake GUIDs — real Entra ID
#: tenant/client IDs are always GUIDs, so _validate_guid rejects
#: plain placeholder strings like "tenant-id" now.
FAKE_TENANT_ID = "12345678-1234-1234-1234-123456789abc"
FAKE_CLIENT_ID = "87654321-4321-4321-4321-cba987654321"


def test_valid_values_are_accepted(clean_env: pytest.MonkeyPatch) -> None:
    """All four required fields, when provided, are accepted as-is."""
    settings = DataverseConnectionSettings(
        azure_tenant_id=FAKE_TENANT_ID,
        azure_client_id=FAKE_CLIENT_ID,
        azure_client_secret="client-secret",
        dataverse_url="https://org.crm.dynamics.com",
    )
    assert settings.azure_tenant_id == FAKE_TENANT_ID
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
            azure_client_id=FAKE_CLIENT_ID,
            azure_client_secret="client-secret",
            dataverse_url="https://org.crm.dynamics.com",
        )


def test_whitespace_is_stripped_from_all_four_fields(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """Leading/trailing whitespace is stripped before validation."""
    settings = DataverseConnectionSettings(
        azure_tenant_id=f"  {FAKE_TENANT_ID}  ",
        azure_client_id=f"  {FAKE_CLIENT_ID}  ",
        azure_client_secret="  client-secret  ",
        dataverse_url="  https://org.crm.dynamics.com  ",
    )
    assert settings.azure_tenant_id == FAKE_TENANT_ID
    assert settings.azure_client_id == FAKE_CLIENT_ID
    assert settings.azure_client_secret == "client-secret"
    assert settings.dataverse_url == "https://org.crm.dynamics.com"


def test_trailing_slash_is_stripped_from_dataverse_url(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """A trailing slash on dataverse_url never double-slashes downstream."""
    settings = DataverseConnectionSettings(
        azure_tenant_id=FAKE_TENANT_ID,
        azure_client_id=FAKE_CLIENT_ID,
        azure_client_secret="client-secret",
        dataverse_url="https://org.crm.dynamics.com/",
    )
    assert settings.dataverse_url == "https://org.crm.dynamics.com"


def test_azure_tenant_id_rejects_a_non_guid_value(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """A plain, non-GUID string is rejected — real tenant IDs are GUIDs."""
    with pytest.raises(ValidationError) as exc_info:
        DataverseConnectionSettings(
            azure_tenant_id="not-a-guid",
            azure_client_id=FAKE_CLIENT_ID,
            azure_client_secret="client-secret",
            dataverse_url="https://org.crm.dynamics.com",
        )

    assert "azure_tenant_id" in str(exc_info.value)


def test_azure_client_id_rejects_a_non_guid_value(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """A plain, non-GUID string is rejected — real client IDs are GUIDs."""
    with pytest.raises(ValidationError) as exc_info:
        DataverseConnectionSettings(
            azure_tenant_id=FAKE_TENANT_ID,
            azure_client_id="not-a-guid",
            azure_client_secret="client-secret",
            dataverse_url="https://org.crm.dynamics.com",
        )

    assert "azure_client_id" in str(exc_info.value)


def test_dataverse_url_rejects_a_url_missing_the_https_scheme(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """A bare hostname with no scheme is rejected, not silently accepted."""
    with pytest.raises(ValidationError) as exc_info:
        DataverseConnectionSettings(
            azure_tenant_id=FAKE_TENANT_ID,
            azure_client_id=FAKE_CLIENT_ID,
            azure_client_secret="client-secret",
            dataverse_url="org.crm.dynamics.com",
        )

    assert "dataverse_url" in str(exc_info.value)


def test_dataverse_url_rejects_a_plain_http_scheme(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """A plain http:// URL is rejected — Dataverse is https-only."""
    with pytest.raises(ValidationError) as exc_info:
        DataverseConnectionSettings(
            azure_tenant_id=FAKE_TENANT_ID,
            azure_client_id=FAKE_CLIENT_ID,
            azure_client_secret="client-secret",
            dataverse_url="http://org.crm.dynamics.com",
        )

    assert "dataverse_url" in str(exc_info.value)


def test_all_four_connection_values_are_vault_backed() -> None:
    """Every field is vault-backed, not just azure_client_secret.

    In a public repository, the tenant ID, client ID, and Dataverse
    URL are real reconnaissance value even though none of them are
    credentials on their own — see README.md's "Secrets Management"
    section for why this covers all four, not just the one true secret.
    """
    assert DataverseConnectionSettings.vault_secret_fields == (
        "azure_tenant_id",
        "azure_client_id",
        "azure_client_secret",
        "dataverse_url",
    )
