"""Unit tests for lag_service_kit.settings.

Covers BaseServiceSettings, find_repo_env_file.
"""

from pathlib import Path
from typing import Any, ClassVar, Dict, Tuple

import pytest
from lag_service_kit.settings import BaseServiceSettings, find_repo_env_file
from pydantic_settings import SettingsConfigDict

pytestmark = pytest.mark.unit


class _FakeKeyVaultSource:
    """Replaces AzureKeyVaultSettingsSource for testing the source chain.

    Never touches the real class at all — these tests are about
    whether ``settings_customise_sources`` includes/excludes and
    orders a Key Vault source correctly, not about
    ``AzureKeyVaultSettingsSource`` itself (covered separately in
    ``test_azure_key_vault.py``).
    """

    def __init__(self, settings_cls: type, vault_url: str) -> None:
        self.settings_cls = settings_cls
        self.vault_url = vault_url

    def __call__(self) -> Dict[str, Any]:
        return {"my_secret": "from-key-vault"}


class _SettingsWithASecret(BaseServiceSettings):
    """A minimal concrete settings class with one vault-backed field."""

    my_secret: str = "unset"

    vault_secret_fields: ClassVar[Tuple[str, ...]] = ("my_secret",)


def test_log_level_defaults_to_info(clean_env: pytest.MonkeyPatch) -> None:
    """log_level defaults to INFO when LOG_LEVEL is unset."""
    settings = BaseServiceSettings()
    assert settings.log_level == "INFO"


def test_log_level_reads_from_environment(
    clean_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """log_level reads from the LOG_LEVEL environment variable."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    settings = BaseServiceSettings()
    assert settings.log_level == "DEBUG"


def test_log_level_strips_surrounding_whitespace(
    clean_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A LOG_LEVEL value with stray whitespace is trimmed before validation."""
    monkeypatch.setenv("LOG_LEVEL", "  DEBUG  ")
    settings = BaseServiceSettings()
    assert settings.log_level == "DEBUG"


def test_find_repo_env_file_locates_env_file_in_an_ancestor_directory(
    tmp_path: Path,
) -> None:
    """find_repo_env_file walks upward and finds a .env in a parent dir."""
    (tmp_path / ".env").write_text("KEY=value\n")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    fake_module_file = nested / "module.py"

    found = find_repo_env_file(fake_module_file)

    assert found == tmp_path / ".env"


def test_find_repo_env_file_returns_none_when_no_env_file_exists(
    tmp_path: Path,
) -> None:
    """find_repo_env_file returns None when no .env exists in any ancestor.

    ``tmp_path`` lives under the OS temp directory, so none of its real
    ancestors (system temp/var directories) are expected to contain a
    ``.env`` file — if one somehow does, that's a genuine anomaly worth
    this test failing loudly on, not silently tolerating.
    """
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    fake_module_file = nested / "module.py"

    found = find_repo_env_file(fake_module_file)

    assert found is None


def test_key_vault_is_never_consulted_when_url_is_unset(
    clean_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no AZURE_KEY_VAULT_URL, settings resolve exactly as before."""
    monkeypatch.setenv("MY_SECRET", "from-env")

    settings = _SettingsWithASecret()

    assert settings.my_secret == "from-env"


def test_key_vault_value_is_used_when_url_is_a_real_env_var(
    clean_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real AZURE_KEY_VAULT_URL env var brings Key Vault into the chain."""
    monkeypatch.setattr(
        "lag_service_kit.settings.AzureKeyVaultSettingsSource",
        _FakeKeyVaultSource,
    )
    monkeypatch.setenv("AZURE_KEY_VAULT_URL", "https://fake.vault.azure.net/")

    settings = _SettingsWithASecret()

    assert settings.my_secret == "from-key-vault"


def test_a_real_env_var_overrides_key_vault(
    clean_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real env var for the field itself still wins over Key Vault."""
    monkeypatch.setattr(
        "lag_service_kit.settings.AzureKeyVaultSettingsSource",
        _FakeKeyVaultSource,
    )
    monkeypatch.setenv("AZURE_KEY_VAULT_URL", "https://fake.vault.azure.net/")
    monkeypatch.setenv("MY_SECRET", "from-real-env-var")

    settings = _SettingsWithASecret()

    assert settings.my_secret == "from-real-env-var"


def test_a_dotenv_only_key_vault_url_never_enables_key_vault(
    clean_env: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AZURE_KEY_VAULT_URL set only in .env does not enable Key Vault.

    If this were wrongly checked via a resolved settings value (or a
    raw os.environ read that happened to also see .env-sourced
    values) instead of the real environment specifically, this test
    would see "from-key-vault" instead of "from-dotenv".
    """
    monkeypatch.setattr(
        "lag_service_kit.settings.AzureKeyVaultSettingsSource",
        _FakeKeyVaultSource,
    )
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AZURE_KEY_VAULT_URL=https://fake.vault.azure.net/\n"
        "MY_SECRET=from-dotenv\n"
    )

    class _SettingsWithEnvFile(_SettingsWithASecret):
        model_config = SettingsConfigDict(env_file=env_file)

    settings = _SettingsWithEnvFile()

    assert settings.my_secret == "from-dotenv"


def test_key_vault_overrides_a_conflicting_dotenv_value(
    clean_env: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Key Vault outranks .env once a real env var actually enables it."""
    monkeypatch.setattr(
        "lag_service_kit.settings.AzureKeyVaultSettingsSource",
        _FakeKeyVaultSource,
    )
    monkeypatch.setenv("AZURE_KEY_VAULT_URL", "https://fake.vault.azure.net/")
    env_file = tmp_path / ".env"
    env_file.write_text("MY_SECRET=from-dotenv\n")

    class _SettingsWithEnvFile(_SettingsWithASecret):
        model_config = SettingsConfigDict(env_file=env_file)

    settings = _SettingsWithEnvFile()

    assert settings.my_secret == "from-key-vault"
