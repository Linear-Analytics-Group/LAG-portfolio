"""Base Pydantic settings shared by every LAG service, plus `.env` discovery."""

from pathlib import Path
from typing import ClassVar, Optional, Type

from lag_service_kit.azure_key_vault import AzureKeyVaultSettingsSource
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

#: The only level names ``logging.config.dictConfig`` accepts. Not
#: read from ``logging`` itself (its name-to-level mapping is a
#: private implementation detail, not public API) — this is the
#: standard, stable set every Python ``logging`` level name belongs
#: to, deliberately excluding the deprecated aliases ``WARN``/``FATAL``.
#: Writing this list out here, instead of introspecting ``logging``'s
#: internals, helps ensure this validator's behavior can't shift under
#: future Python version renames or restructures to that private
#: mapping — this set only changes if we deliberately change it.
_VALID_LOG_LEVELS: frozenset[str] = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
)


def find_repo_env_file(start: Path) -> Optional[Path]:
    """Walk upward from a starting file looking for a `.env` file.

    Mirrors ``python-dotenv``'s default discovery behavior, so a service
    can locate its repository-root `.env` file without hardcoding how many
    directory levels separate its own module from that root.

    Parameters
    ----------
    start : Path
        The file to begin the upward search from, typically a service's
        own ``__file__``.

    Returns
    -------
    Optional[Path]
        The path to the nearest `.env` file among ``start``'s parent
        directories, or ``None`` if none is found before reaching the
        filesystem root.
    """
    for directory in start.resolve().parents:
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


class BaseServiceSettings(BaseSettings):
    """Runtime configuration fields common to every LAG service.

    Concrete services subclass this (typically alongside a domain-specific
    mixin such as ``DataverseConnectionSettings``) and supply their own
    ``model_config`` with an ``env_file`` resolved via
    :func:`find_repo_env_file`.

    Parameters
    ----------
    log_level : str
        Root logging level for the service's structured logging matrix.
        Read from the ``LOG_LEVEL`` environment variable. Defaults to
        ``"INFO"``.
    azure_key_vault_url : str, optional
        URL of an Azure Key Vault to resolve secret fields from (see
        ``vault_secret_fields``). Read from the ``AZURE_KEY_VAULT_URL``
        environment variable. When unset, no Key Vault lookup is ever
        attempted and every field resolves from environment variables
        or `.env` exactly as it always has — this is an optional
        upgrade, not a requirement.

    Notes
    -----
    ``vault_secret_fields`` is a class variable, not a pydantic field
    (excluded from the model via ``ClassVar``) — it declares *which*
    fields a concrete settings class considers true secrets, not a
    runtime value. Empty here; a mixin that actually owns a secret
    (e.g. ``DataverseConnectionSettings.azure_client_secret``) overrides
    it, the same declared-but-not-defined pattern already used
    elsewhere in this codebase for a domain-owned attribute.
    """

    log_level: str = Field(default="INFO")
    azure_key_vault_url: Optional[str] = Field(default=None)

    vault_secret_fields: ClassVar[tuple[str, ...]] = ()

    @field_validator("log_level", "azure_key_vault_url", mode="before")
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

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        """Confirm log_level names a real logging level, normalize case.

        Parameters
        ----------
        value : str
            The whitespace-stripped log level value.

        Returns
        -------
        str
            ``value``, uppercased, so every consumer of
            ``settings.log_level`` sees one canonical form regardless
            of how it was cased in the environment or `.env` file.

        Raises
        ------
        ValueError
            If ``value.upper()`` isn't one of
            :data:`_VALID_LOG_LEVELS`. Raised here, at settings
            construction time, rather than letting an invalid value
            reach ``lag_service_kit.logging.configure_logging()`` —
            which raises a plain ``ValueError`` of its own, not a
            ``pydantic.ValidationError``, so it would otherwise fall
            through every specific ``except`` clause in
            ``BaseSyncRunner.run()`` and get logged as an "unexpected
            error" instead of the clear configuration error it is.
        """
        if value.upper() not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of "
                f"{sorted(_VALID_LOG_LEVELS)}, got {value!r}."
            )
        return value.upper()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Insert an Azure Key Vault source when one is configured.

        Parameters
        ----------
        settings_cls : Type[BaseSettings]
            The concrete settings class being resolved.
        init_settings : PydanticBaseSettingsSource
            Values passed directly to the constructor.
        env_settings : PydanticBaseSettingsSource
            Real process environment variables.
        dotenv_settings : PydanticBaseSettingsSource
            Values from a `.env` file.
        file_secret_settings : PydanticBaseSettingsSource
            Values from Docker/Kubernetes-style secret files.

        Returns
        -------
        tuple[PydanticBaseSettingsSource, ...]
            The sources pydantic-settings will try, in priority order
            (first wins): constructor kwargs, then real environment
            variables, then — only when ``AZURE_KEY_VAULT_URL`` is
            actually set — Key Vault, then `.env`, then secret files.
            A real environment variable always overrides Key Vault,
            which always overrides `.env`; Key Vault is absent from
            the chain entirely (not merely empty) when unconfigured,
            so it costs nothing and changes nothing for a deployment
            that never sets ``AZURE_KEY_VAULT_URL``.

        Notes
        -----
        Decides whether Key Vault is configured by calling
        ``env_settings()`` itself — the same
        ``pydantic_settings.EnvSettingsSource`` pydantic-settings would
        use anyway — rather than reading ``os.environ`` directly. This
        reuses this class's own ``case_sensitive``/encoding
        configuration instead of duplicating it, and deliberately does
        *not* consult ``dotenv_settings``: a `.env`-only value never
        enables Key Vault, so the local-only fallback path can never be
        surprised into making a live network call it didn't ask for.
        """
        sources = [init_settings, env_settings]

        vault_url = env_settings().get("azure_key_vault_url")
        if isinstance(vault_url, str) and vault_url.strip():
            sources.append(
                AzureKeyVaultSettingsSource(settings_cls, vault_url.strip())
            )

        sources.extend([dotenv_settings, file_secret_settings])
        return tuple(sources)
