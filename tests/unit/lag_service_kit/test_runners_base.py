"""Unit tests for lag_service_kit.runners.base.BaseSyncRunner's template method.

Exercised through a minimal concrete test double, confirming ``run()``
calls its four hooks in the fixed order the template method promises,
and that its exit-code decision is correct — in isolation from any real
destination's ``sync_records()`` implementation. Whether ``sync_records()``
itself keeps processing the rest of a batch after one record fails is a
property of *that* method (see ``BaseODataInventorySyncRunner``'s own
tests and the acceptance-level idempotency tests), not of ``run()``:
here, ``sync_records()`` is a stub returning a result dict directly, and
these tests only check that ``run()`` interprets that dict correctly.
"""

from typing import Any, Dict, List

import pandas as pd
import pytest
from lag_data_utils.clients.base import AuthenticationError, BaseClient
from lag_service_kit.runners import BaseSyncRunner
from lag_service_kit.validation import RecordValidationError
from pydantic import BaseModel, ValidationError

pytestmark = pytest.mark.unit


class _FakeSettings(BaseModel):
    log_level: str = "INFO"


class _RequiredFieldProbe(BaseModel):
    """A minimal model used only to manufacture a real validation error."""

    required_field: str


def _build_validation_error() -> ValidationError:
    """Produce a real ``ValidationError`` with zero environment dependency."""
    try:
        _RequiredFieldProbe()  # type: ignore[call-arg]
    except ValidationError as exc:
        return exc
    raise AssertionError("expected ValidationError was not raised")


class _FakeClient(BaseClient):
    def acquire_bearer_token(self) -> str:
        return "fake-token"


class _RecordingRunner(BaseSyncRunner[_FakeClient]):
    """Records the hook call order, so run()'s sequence can be asserted."""

    def __init__(self, fail_settings: bool = False, fail_auth: bool = False):
        self.calls: List[str] = []
        self._fail_settings = fail_settings
        self._client = _FakeClient()
        if fail_auth:
            self._client.acquire_bearer_token = (  # type: ignore[method-assign]
                self._raise_auth_error
            )

    def _raise_auth_error(self) -> str:
        raise AuthenticationError("boom")

    def load_settings(self) -> Any:
        self.calls.append("load_settings")
        if self._fail_settings:
            raise _build_validation_error()
        return _FakeSettings()

    def build_client(self, settings: Any) -> _FakeClient:
        self.calls.append("build_client")
        return self._client

    def load_records(self) -> pd.DataFrame:
        self.calls.append("load_records")
        return pd.DataFrame([{"id": 1}, {"id": 2}])

    def sync_records(
        self, client: Any, records: pd.DataFrame
    ) -> Dict[str, int]:
        self.calls.append("sync_records")
        return {"created": len(records), "updated": 0, "failed": 0}


def test_run_calls_hooks_in_the_documented_order() -> None:
    """load_settings -> build_client -> load_records -> sync_records."""
    runner = _RecordingRunner()

    exit_code = runner.run()

    assert exit_code == 0
    assert runner.calls == [
        "load_settings",
        "build_client",
        "load_records",
        "sync_records",
    ]


def test_run_returns_zero_when_nothing_failed() -> None:
    """A clean sync (zero failed records) exits 0."""
    assert _RecordingRunner().run() == 0


def test_run_reports_failure_even_when_most_records_succeeded() -> None:
    """run()'s exit code reflects a nonzero failed count either way.

    This deliberately does *not* test whether sync_records() kept
    processing records after a failure — that's
    BaseODataInventorySyncRunner's own responsibility, covered
    separately. Here, sync_records() is a stub that returns
    created=5, failed=1 directly, to make unambiguous that most of a
    batch succeeded and run() still correctly reports overall failure.
    """

    class _MostlySucceededRunner(_RecordingRunner):
        def sync_records(
            self, client: Any, records: pd.DataFrame
        ) -> Dict[str, int]:
            return {"created": 5, "updated": 0, "failed": 1}

    assert _MostlySucceededRunner().run() == 1


def test_run_returns_one_and_short_circuits_on_configuration_error() -> None:
    """A ValidationError from load_settings() stops before build_client()."""
    runner = _RecordingRunner(fail_settings=True)

    exit_code = runner.run()

    assert exit_code == 1
    assert runner.calls == ["load_settings"]


def test_run_returns_one_and_short_circuits_on_authentication_error() -> None:
    """An AuthenticationError from the client stops before load_records()."""
    runner = _RecordingRunner(fail_auth=True)

    exit_code = runner.run()

    assert exit_code == 1
    assert runner.calls == ["load_settings", "build_client"]


def test_run_reports_a_source_error_when_load_records_raises(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing source feed is reported distinctly, not as a generic bug."""

    class _MissingSourceRunner(_RecordingRunner):
        def load_records(self) -> pd.DataFrame:
            self.calls.append("load_records")
            raise FileNotFoundError("mock_feed.csv not found")

    exit_code = _MissingSourceRunner().run()

    assert exit_code == 1
    assert "Source error" in capsys.readouterr().out


def test_run_reports_a_data_validation_error_distinctly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A malformed feed is reported distinctly, not as a generic bug.

    Mirrors the FileNotFoundError/"Source error" test above: a
    RecordValidationError from load_records() gets its own clear,
    logged category rather than falling into the generic "Unexpected
    error during sync." branch.
    """

    class _MalformedFeedRunner(_RecordingRunner):
        def load_records(self) -> pd.DataFrame:
            self.calls.append("load_records")
            raise RecordValidationError("Missing required column(s): sku_id.")

    exit_code = _MalformedFeedRunner().run()

    assert exit_code == 1
    assert "Data validation error" in capsys.readouterr().out


def test_run_reports_unexpected_errors_instead_of_crashing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A bug in a hook is caught, logged with a traceback, and reported."""

    class _BuggyRunner(_RecordingRunner):
        def build_client(self, settings: Any) -> _FakeClient:
            self.calls.append("build_client")
            raise RuntimeError("not a business failure, a bug")

    exit_code = _BuggyRunner().run()

    assert exit_code == 1
    assert "Unexpected error during sync." in capsys.readouterr().out
