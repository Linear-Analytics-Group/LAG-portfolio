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
from pydantic import BaseModel, ValidationError

pytestmark = pytest.mark.unit


class _FakeSettings(BaseModel):
    log_level: str = "INFO"


class _RequiredFieldProbe(BaseModel):
    """A minimal model used only to manufacture a real ``pydantic.ValidationError``."""

    required_field: str


def _build_validation_error() -> ValidationError:
    """Produce a real ``pydantic.ValidationError`` with zero environment dependency."""
    try:
        _RequiredFieldProbe()  # type: ignore[call-arg]
    except ValidationError as exc:
        return exc
    raise AssertionError("expected ValidationError was not raised")


class _FakeClient(BaseClient):
    def acquire_bearer_token(self) -> str:
        return "fake-token"


class _RecordingRunner(BaseSyncRunner[_FakeClient]):
    """Records the order hooks are called in, so run()'s sequence can be asserted on."""

    def __init__(self, fail_settings: bool = False, fail_auth: bool = False):
        self.calls: List[str] = []
        self._fail_settings = fail_settings
        self._client = _FakeClient()
        if fail_auth:
            self._client.acquire_bearer_token = self._raise_auth_error  # type: ignore[method-assign]

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

    def sync_records(self, client: Any, records: pd.DataFrame) -> Dict[str, int]:
        self.calls.append("sync_records")
        return {"created": len(records), "updated": 0, "failed": 0}


def test_run_calls_hooks_in_the_documented_order() -> None:
    """load_settings -> build_client -> acquire_bearer_token -> load_records -> sync_records."""
    runner = _RecordingRunner()

    exit_code = runner.run()

    assert exit_code == 0
    assert runner.calls == ["load_settings", "build_client", "load_records", "sync_records"]


def test_run_returns_zero_when_nothing_failed() -> None:
    """A clean sync (zero failed records) exits 0."""
    assert _RecordingRunner().run() == 0


def test_run_reports_failure_via_exit_code_even_when_most_records_succeeded() -> None:
    """run()'s exit code reflects a nonzero failed count, independent of how sync_records got there.

    This deliberately does *not* test whether sync_records() kept
    processing records after a failure — that's
    BaseODataInventorySyncRunner's own responsibility, covered
    separately. Here, sync_records() is a stub that returns
    created=5, failed=1 directly, to make unambiguous that most of a
    batch succeeded and run() still correctly reports overall failure.
    """

    class _MostlySucceededRunner(_RecordingRunner):
        def sync_records(self, client: Any, records: pd.DataFrame) -> Dict[str, int]:
            return {"created": 5, "updated": 0, "failed": 1}

    assert _MostlySucceededRunner().run() == 1


def test_run_returns_one_and_short_circuits_on_configuration_error() -> None:
    """A ValidationError from load_settings() is caught, logged, and stops before build_client()."""
    runner = _RecordingRunner(fail_settings=True)

    exit_code = runner.run()

    assert exit_code == 1
    assert runner.calls == ["load_settings"]


def test_run_returns_one_and_short_circuits_on_authentication_error() -> None:
    """An AuthenticationError from acquire_bearer_token() is caught and stops before load_records()."""
    runner = _RecordingRunner(fail_auth=True)

    exit_code = runner.run()

    assert exit_code == 1
    assert runner.calls == ["load_settings", "build_client"]
