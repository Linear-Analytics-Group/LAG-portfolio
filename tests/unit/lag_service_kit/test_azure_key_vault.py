"""Unit tests for lag_service_kit.azure_key_vault.AzureKeyVaultSettingsSource.

Never constructs a real SecretClient or DefaultAzureCredential — every
test injects a fake client via the constructor, so nothing here makes
a real network call or needs real Azure credentials.
"""

from types import SimpleNamespace
from typing import ClassVar, Dict, List, Tuple

import pytest
from azure.core.exceptions import ResourceNotFoundError
from lag_service_kit.azure_key_vault import AzureKeyVaultSettingsSource
from pydantic_settings import BaseSettings

pytestmark = pytest.mark.unit

FAKE_VAULT_URL = "https://fake.vault.azure.net/"


class _FakeSecretClient:
    """A controllable stand-in for azure.keyvault.secrets.SecretClient.

    Satisfies ``AzureKeyVaultSettingsSource``'s ``_SecretClientLike``
    Protocol purely structurally — this class has no inheritance
    relationship to the real SDK's ``SecretClient`` at all, and needs
    none, because the constructor it's passed to is typed against the
    Protocol rather than the concrete class.
    """

    def __init__(self, secrets: Dict[str, str]) -> None:
        self._secrets = secrets
        self.requested_names: List[str] = []

    def get_secret(self, name: str) -> SimpleNamespace:
        self.requested_names.append(name)
        if name not in self._secrets:
            raise ResourceNotFoundError(f"Secret '{name}' not found.")
        return SimpleNamespace(value=self._secrets[name])


class _StubSettings(BaseSettings):
    """A minimal settings class declaring exactly one vault-backed field."""

    plain_field: str = "unset"
    secret_field: str = "unset"

    vault_secret_fields: ClassVar[Tuple[str, ...]] = ("secret_field",)


def test_non_vault_field_returns_none_without_a_client_call() -> None:
    """A field outside vault_secret_fields is skipped, with no client call."""
    client = _FakeSecretClient({})
    source = AzureKeyVaultSettingsSource(
        _StubSettings, FAKE_VAULT_URL, secret_client=client
    )

    value, key, is_complex = source.get_field_value(
        _StubSettings.model_fields["plain_field"], "plain_field"
    )

    assert value is None
    assert key == "plain_field"
    assert is_complex is False
    assert client.requested_names == []


def test_declared_vault_field_is_fetched_with_a_hyphenated_name() -> None:
    """A declared field is fetched, translating underscores to hyphens."""
    client = _FakeSecretClient({"secret-field": "fetched-value"})
    source = AzureKeyVaultSettingsSource(
        _StubSettings, FAKE_VAULT_URL, secret_client=client
    )

    value, key, _ = source.get_field_value(
        _StubSettings.model_fields["secret_field"], "secret_field"
    )

    assert value == "fetched-value"
    assert key == "secret_field"
    assert client.requested_names == ["secret-field"]


def test_missing_declared_secret_raises_instead_of_falling_through() -> None:
    """A declared-but-absent vault secret raises — it never falls through.

    A field explicitly marked vault-backed but missing from the vault
    is a real setup mistake (see the class's own docstring); silently
    falling back to .env would hide that mistake instead of surfacing it.
    """
    client = _FakeSecretClient({})  # "secret-field" deliberately absent
    source = AzureKeyVaultSettingsSource(
        _StubSettings, FAKE_VAULT_URL, secret_client=client
    )

    with pytest.raises(ResourceNotFoundError):
        source.get_field_value(
            _StubSettings.model_fields["secret_field"], "secret_field"
        )


def test_call_resolves_only_the_declared_vault_field() -> None:
    """__call__() returns only vault-backed fields, omitting every other."""
    client = _FakeSecretClient({"secret-field": "fetched-value"})
    source = AzureKeyVaultSettingsSource(
        _StubSettings, FAKE_VAULT_URL, secret_client=client
    )

    resolved = source()

    assert resolved == {"secret_field": "fetched-value"}


def test_prepare_field_value_passes_the_value_through_unchanged() -> None:
    """prepare_field_value() applies no transformation of its own."""
    source = AzureKeyVaultSettingsSource(
        _StubSettings, FAKE_VAULT_URL, secret_client=_FakeSecretClient({})
    )

    result = source.prepare_field_value(
        "secret_field", _StubSettings.model_fields["secret_field"], "raw", False
    )

    assert result == "raw"
