"""Business requirement: operable beyond simple execution.

Configuration errors, authentication failures, and per-record write
failures must all be surfaced clearly (not swallowed silently) and must
not crash the process with an unhandled exception — ``run()`` always
returns a definite exit code. A single bad record must not stop the rest
of the batch from syncing.
"""

import re
from typing import Callable

import pytest
import requests
import responses
from lag_data_utils.clients.dataverse import (
    DataverseAuthenticationError,
    DataverseClient,
)
from pydantic import BaseModel, ValidationError
from runners.dataverse import DataverseInventorySyncRunner
from sources import CsvInventorySource

pytestmark = pytest.mark.acceptance

UPSERT_URL_PATTERN = re.compile(
    r".*/lagsol_inventoryitems\(lagsol_skuid='.*'\)$"
)


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


def test_missing_configuration_is_reported_and_run_fails(
    dataverse_runner_factory: Callable[..., DataverseInventorySyncRunner],
    csv_source: CsvInventorySource,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A configuration error is logged and reported via a definite exit code."""
    runner = dataverse_runner_factory(csv_source)
    validation_error = _build_validation_error()
    monkeypatch.setattr(
        runner, "load_settings", lambda: (_ for _ in ()).throw(validation_error)
    )

    exit_code = runner.run()

    assert exit_code == 1
    assert "Configuration error" in capsys.readouterr().out


def test_authentication_failure_is_reported_and_run_fails(
    dataverse_runner_factory: Callable[..., DataverseInventorySyncRunner],
    csv_source: CsvInventorySource,
    dataverse_client: DataverseClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An Entra ID auth failure is logged and reported via an exit code."""

    def _raise_auth_error() -> str:
        raise DataverseAuthenticationError(
            "Entra ID rejected the client credentials."
        )

    monkeypatch.setattr(
        dataverse_client, "acquire_bearer_token", _raise_auth_error
    )
    runner = dataverse_runner_factory(csv_source)

    exit_code = runner.run()

    assert exit_code == 1
    assert "Authentication error" in capsys.readouterr().out


@responses.activate
def test_one_failed_record_does_not_stop_the_rest_from_syncing(
    dataverse_runner_factory: Callable[..., DataverseInventorySyncRunner],
    csv_source: CsvInventorySource,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One record's HTTP failure is counted and logged; the batch continues."""
    responses.add(
        responses.PATCH,
        re.compile(r".*/lagsol_inventoryitems\(lagsol_skuid='SKU-002'\)$"),
        status=500,
    )
    responses.add(responses.PATCH, UPSERT_URL_PATTERN, status=201)

    exit_code = dataverse_runner_factory(csv_source).run()

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "2 created, 0 updated, 1 failed (of 3 records)" in output
    assert "FAILED sku_id=SKU-002" in output


@responses.activate
def test_a_dropped_connection_on_one_record_does_not_stop_the_rest(
    dataverse_runner_factory: Callable[..., DataverseInventorySyncRunner],
    csv_source: CsvInventorySource,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A network failure on one record is counted like an HTTP failure."""
    responses.add(
        responses.PATCH,
        re.compile(r".*/lagsol_inventoryitems\(lagsol_skuid='SKU-002'\)$"),
        body=requests.ConnectionError("Connection reset by peer"),
    )
    responses.add(responses.PATCH, UPSERT_URL_PATTERN, status=201)

    exit_code = dataverse_runner_factory(csv_source).run()

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "2 created, 0 updated, 1 failed (of 3 records)" in output
    assert "FAILED sku_id=SKU-002: ConnectionError" in output
