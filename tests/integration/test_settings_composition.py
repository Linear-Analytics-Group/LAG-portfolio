"""Integration: InventorySyncSettings composes the lag_service_kit mixins correctly.

Every field asserted here comes from environment variables set explicitly
in each test via ``monkeypatch``, which always take priority over
whatever a real local ``.env`` file happens to contain — these tests are
hermetic regardless of the machine they run on.
"""

import pytest
from config import InventorySyncSettings
from lag_data_utils.clients.dataverse import DataverseConnectionSettings as ClientSideProtocol


def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_TENANT_ID", "test-tenant-id")
    monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("DATAVERSE_URL", "https://test-org.crm.dynamics.com/")


@pytest.mark.integration
def test_settings_compose_dataverse_and_service_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """InventorySyncSettings exposes both Dataverse connection fields and log_level."""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = InventorySyncSettings()  # type: ignore[call-arg]

    assert settings.azure_tenant_id == "test-tenant-id"
    assert settings.azure_client_id == "test-client-id"
    assert settings.azure_client_secret == "test-client-secret"
    assert settings.dataverse_url == "https://test-org.crm.dynamics.com"  # trailing slash stripped
    assert settings.log_level == "DEBUG"


@pytest.mark.integration
def test_log_level_defaults_to_info_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """log_level defaults to INFO when LOG_LEVEL is not set, without affecting required fields."""
    _set_required_env(monkeypatch)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = InventorySyncSettings()  # type: ignore[call-arg]

    assert settings.log_level == "INFO"


@pytest.mark.integration
def test_settings_satisfy_lag_data_utils_protocol_structurally(monkeypatch: pytest.MonkeyPatch) -> None:
    """An InventorySyncSettings instance satisfies lag_data_utils's Protocol via structural typing.

    lag_data_utils never imports lag_service_kit or Pydantic — this
    proves the two packages' independently-defined shapes still line up.
    """
    _set_required_env(monkeypatch)

    settings = InventorySyncSettings()  # type: ignore[call-arg]

    assert isinstance(settings, ClientSideProtocol)
