"""Unit tests for lag_service_kit.settings: BaseServiceSettings, find_repo_env_file."""

from pathlib import Path

from lag_service_kit.settings import BaseServiceSettings, find_repo_env_file


def test_log_level_defaults_to_info(clean_env):
    """log_level defaults to INFO when LOG_LEVEL is unset."""
    settings = BaseServiceSettings()
    assert settings.log_level == "INFO"


def test_log_level_reads_from_environment(clean_env, monkeypatch):
    """log_level reads from the LOG_LEVEL environment variable."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    settings = BaseServiceSettings()
    assert settings.log_level == "DEBUG"


def test_log_level_strips_surrounding_whitespace(clean_env, monkeypatch):
    """A LOG_LEVEL value with stray whitespace is trimmed before validation."""
    monkeypatch.setenv("LOG_LEVEL", "  DEBUG  ")
    settings = BaseServiceSettings()
    assert settings.log_level == "DEBUG"


def test_find_repo_env_file_locates_env_file_in_an_ancestor_directory(tmp_path: Path):
    """find_repo_env_file walks upward and finds a .env file in a parent directory."""
    (tmp_path / ".env").write_text("KEY=value\n")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    fake_module_file = nested / "module.py"

    found = find_repo_env_file(fake_module_file)

    assert found == tmp_path / ".env"


def test_find_repo_env_file_returns_none_when_no_env_file_exists(tmp_path: Path):
    """find_repo_env_file returns None when no .env file exists among any ancestor.

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
