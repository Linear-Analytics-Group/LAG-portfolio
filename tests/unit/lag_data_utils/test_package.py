"""Unit tests for lag_data_utils's own package metadata.

Covers __version__.
"""

import lag_data_utils
import pytest

pytestmark = pytest.mark.unit


def test_version_is_a_non_empty_string() -> None:
    """__version__ resolves to a real, non-empty version string.

    A successful import already proves the package name passed to
    importlib.metadata.version() in __init__.py is correct — a typo
    there would raise importlib.metadata.PackageNotFoundError at
    import time, failing every test in this suite, not just this one.
    """
    assert isinstance(lag_data_utils.__version__, str)
    assert lag_data_utils.__version__ != ""
