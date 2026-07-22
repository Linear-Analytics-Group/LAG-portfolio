"""Integration: InventorySyncSettings composes the lag_service_kit mixins.

Every field asserted here comes from environment variables set explicitly
in each test via ``monkeypatch``, which always take priority over
whatever a real local ``.env`` file happens to contain — these tests are
hermetic regardless of the machine they run on.
"""

import pytest
from config import InventorySyncSettings
from lag_data_utils.clients.dataverse import (
    DataverseConnectionSettings as ClientSideProtocol,
)


def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_TENANT_ID", "test-tenant-id")
    monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("DATAVERSE_URL", "https://test-org.crm.dynamics.com/")


@pytest.mark.integration
def test_settings_compose_dataverse_and_service_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """InventorySyncSettings exposes Dataverse fields and log_level."""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = InventorySyncSettings()

    assert settings.azure_tenant_id == "test-tenant-id"
    assert settings.azure_client_id == "test-client-id"
    assert settings.azure_client_secret == "test-client-secret"
    # Trailing slash stripped.
    assert settings.dataverse_url == "https://test-org.crm.dynamics.com"
    assert settings.log_level == "DEBUG"


@pytest.mark.integration
def test_log_level_defaults_to_info_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """log_level defaults to INFO without affecting required fields."""
    _set_required_env(monkeypatch)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = InventorySyncSettings()

    assert settings.log_level == "INFO"


@pytest.mark.integration
def test_settings_satisfy_lag_data_utils_protocol_structurally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An InventorySyncSettings satisfies lag_data_utils's Protocol.

    lag_data_utils never imports lag_service_kit or Pydantic — this
    proves the two packages' independently-defined shapes still line up.
    """
    _set_required_env(monkeypatch)

    settings = InventorySyncSettings()

    assert isinstance(settings, ClientSideProtocol)


@pytest.mark.integration
def test_settings_resolve_all_four_dataverse_fields_from_key_vault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """InventorySyncSettings itself, not just a test-local stand-in,

    pulls all four Dataverse connection fields from Key Vault when
    AZURE_KEY_VAULT_URL is set — proving the real composed settings
    class actually wires up DataverseConnectionSettings's
    vault_secret_fields correctly, not only BaseServiceSettings's
    mechanism in isolation (see test_settings.py for that).
    """

    class _FakeKeyVaultSource:
        def __init__(self, settings_cls: type, vault_url: str) -> None:
            pass

        def __call__(self) -> dict:  # type: ignore[type-arg]
            return {
                "azure_tenant_id": "vault-tenant-id",
                "azure_client_id": "vault-client-id",
                "azure_client_secret": "vault-client-secret",
                "dataverse_url": "https://vault-org.crm.dynamics.com",
            }

    monkeypatch.setattr(
        "lag_service_kit.settings.AzureKeyVaultSettingsSource",
        _FakeKeyVaultSource,
    )
    monkeypatch.setenv("AZURE_KEY_VAULT_URL", "https://fake.vault.azure.net/")
    # Deliberately not set — proving the four values below come from
    # Key Vault, not a coincidentally-matching real environment variable.
    monkeypatch.delenv("AZURE_TENANT_ID", raising=False)
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("DATAVERSE_URL", raising=False)

    settings = InventorySyncSettings()

    assert settings.azure_tenant_id == "vault-tenant-id"
    assert settings.azure_client_id == "vault-client-id"
    assert settings.azure_client_secret == "vault-client-secret"
    assert settings.dataverse_url == "https://vault-org.crm.dynamics.com"
