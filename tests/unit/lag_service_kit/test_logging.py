"""Unit tests for lag_service_kit.logging.configure_logging."""

import json
import logging

import pytest
from lag_service_kit.logging import configure_logging

pytestmark = pytest.mark.unit


def test_configure_logging_sets_the_root_logger_level() -> None:
    """The effective level matches log_level, case-insensitively."""
    configure_logging("debug")
    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG

    configure_logging("WARNING")
    assert logging.getLogger().getEffectiveLevel() == logging.WARNING


def test_configure_logging_defaults_to_info() -> None:
    """Calling with no argument defaults the root logger to INFO."""
    configure_logging()
    assert logging.getLogger().getEffectiveLevel() == logging.INFO


def test_configure_logging_rejects_an_unknown_level_name() -> None:
    """An unrecognized level name raises rather than silently defaulting."""
    with pytest.raises(ValueError):
        configure_logging("NOT_A_REAL_LEVEL")


def test_configure_logging_installs_exactly_one_console_handler() -> None:
    """Repeated calls don't accumulate duplicate handlers on the root logger."""
    configure_logging("INFO")
    configure_logging("INFO")

    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0], logging.StreamHandler)


def test_a_logged_line_is_valid_single_line_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every emitted line parses as one JSON object, not human-formatted text.

    This is the core "structured logging" claim itself: a log
    aggregator must be able to parse each line natively, with no
    custom parsing rule of its own.
    """
    configure_logging("INFO")
    logger = logging.getLogger("test.structured_logging")

    logger.info("Sync complete")

    line = capsys.readouterr().out.strip()
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.structured_logging"
    assert payload["message"] == "Sync complete"
    assert "timestamp" in payload


def test_extra_fields_are_emitted_as_independent_json_keys(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A call site's extra= fields surface as their own JSON keys.

    Not folded into the message string — the whole point of
    structured logging is that a field like ``sku_id`` is filterable
    on its own, without parsing ``message``.
    """
    configure_logging("INFO")
    logger = logging.getLogger("test.structured_logging")

    logger.error(
        "FAILED sku_id=SKU-1",
        extra={"sku_id": "SKU-1", "exception_type": "HTTPError"},
    )

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["sku_id"] == "SKU-1"
    assert payload["exception_type"] == "HTTPError"


def test_exception_info_is_captured_under_its_own_key(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """logger.exception() adds a formatted traceback under "exception"."""
    configure_logging("INFO")
    logger = logging.getLogger("test.structured_logging")

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("Unexpected error during sync.")

    payload = json.loads(capsys.readouterr().out.strip())
    assert "ValueError: boom" in payload["exception"]


def test_an_extra_field_colliding_with_a_logrecord_attribute_raises() -> None:
    """A colliding extra= key raises KeyError before this formatter runs.

    Documents a real constraint call sites must respect: "created",
    "name", "module", and similar are already LogRecord attributes,
    so an extra= key of the same name is rejected by
    logging.Logger.makeRecord() itself, not by JsonFormatter.
    """
    configure_logging("INFO")
    logger = logging.getLogger("test.structured_logging")

    with pytest.raises(KeyError):
        logger.info("Sync complete", extra={"created": 5})
