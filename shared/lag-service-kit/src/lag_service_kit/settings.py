"""Base Pydantic settings shared by every LAG service, plus `.env` discovery."""

from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


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
    """

    log_level: str = Field(default="INFO")

    @field_validator("log_level", mode="before")
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
