"""Structured logging configuration shared by every LAG service."""

import logging
import logging.config
import sys
from typing import Any, Dict


def configure_logging(log_level: str = "INFO") -> None:
    """Configure the structured logging matrix for a LAG service.

    Installs a single ``StreamHandler`` on the root logger, writing to
    ``stdout`` with a formatter that includes a timestamp, level, logger
    name, and message. Replaces raw ``print()`` calls as a service's sole
    output mechanism.

    Parameters
    ----------
    log_level : str
        The minimum severity level the root logger will emit, as a
        standard ``logging`` level name (e.g., ``"DEBUG"``, ``"INFO"``,
        ``"WARNING"``, ``"ERROR"``). Defaults to ``"INFO"``.

    Returns
    -------
    None

    Raises
    ------
    ValueError
        If ``log_level`` does not correspond to a valid ``logging`` level
        name.
    """
    logging_config: Dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S%z",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "structured",
                "stream": sys.stdout,
            },
        },
        "root": {
            "level": log_level.upper(),
            "handlers": ["console"],
        },
    }
    logging.config.dictConfig(logging_config)
