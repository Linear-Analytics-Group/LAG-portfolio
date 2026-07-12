"""Unit tests for lag_service_kit.logging.configure_logging."""

import logging

import pytest
from lag_service_kit.logging import configure_logging

pytestmark = pytest.mark.unit


def test_configure_logging_sets_the_root_logger_level() -> None:
    """The root logger's effective level matches the requested log_level, case-insensitively."""
    configure_logging("debug")
    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG

    configure_logging("WARNING")
    assert logging.getLogger().getEffectiveLevel() == logging.WARNING


def test_configure_logging_defaults_to_info() -> None:
    """Calling with no argument defaults the root logger to INFO."""
    configure_logging()
    assert logging.getLogger().getEffectiveLevel() == logging.INFO


def test_configure_logging_rejects_an_unknown_level_name() -> None:
    """An unrecognized level name raises ValueError rather than silently defaulting."""
    with pytest.raises(ValueError):
        configure_logging("NOT_A_REAL_LEVEL")


def test_configure_logging_installs_exactly_one_console_handler() -> None:
    """Repeated calls don't accumulate duplicate handlers on the root logger."""
    configure_logging("INFO")
    configure_logging("INFO")

    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0], logging.StreamHandler)
