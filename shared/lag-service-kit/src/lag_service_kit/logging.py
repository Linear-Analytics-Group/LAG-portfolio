"""Structured logging configuration shared by every LAG service."""

import json
import logging
import logging.config
import sys
from typing import Any, Dict, FrozenSet

#: Every attribute a plain ``logging.LogRecord`` carries before any
#: call-site ``extra=`` fields are added, computed from a throwaway
#: record rather than hardcoded so it stays correct across Python
#: versions that add or remove ``LogRecord`` attributes (e.g. 3.12's
#: ``taskName``).
_STANDARD_RECORD_ATTRS: FrozenSet[str] = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
    ).__dict__.keys()
) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Renders each log record as one JSON object per line.

    Every field a log-aggregation platform (Azure Monitor Log
    Analytics, Datadog, ELK/Splunk) needs to filter or alert on —
    ``sku_id``, an exception's type name, a failure count — is emitted
    as its own JSON key, via the call site's ``extra=`` argument,
    rather than folded into the ``message`` string. A message string
    requires a custom parsing rule that breaks the moment wording
    changes; a JSON key does not.

    Notes
    -----
    A call site's ``extra=`` key must not collide with a standard
    ``logging.LogRecord`` attribute name (e.g. ``created``, ``name``,
    ``module``) — ``logging.Logger.makeRecord()`` raises ``KeyError``
    for any ``extra=`` key that shadows one, before this formatter (or
    even the target logger's handler) ever runs. Prefer a
    domain-specific or prefixed key (``records_created``, not
    ``created``) at every call site.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Render one log record as a single-line JSON string.

        Parameters
        ----------
        record : logging.LogRecord
            The record being emitted.

        Returns
        -------
        str
            A JSON object with ``timestamp``, ``level``, ``logger``,
            and ``message`` keys, plus one key per ``extra=`` field
            the call site attached, and an ``exception`` key holding
            the formatted traceback when the record carries exception
            info (i.e. was logged via ``logger.exception()`` or with
            ``exc_info=True``). Any ``extra`` value that is not
            natively JSON-serializable is rendered via ``str()``
            rather than raising, since a logging call must never
            itself crash the caller.
        """
        payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(log_level: str = "INFO") -> None:
    """Configure the structured logging matrix for a LAG service.

    Installs a single ``StreamHandler`` on the root logger, writing to
    ``stdout`` with a :class:`JsonFormatter` — one self-describing JSON
    object per line, not a human-formatted string requiring a custom
    parser downstream. Replaces raw ``print()`` calls as a service's
    sole output mechanism.

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
                "()": JsonFormatter,
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
