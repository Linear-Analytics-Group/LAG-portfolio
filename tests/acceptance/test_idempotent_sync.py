"""Business requirement: sync inventory records into Dataverse idempotently.

Re-running the sync must never duplicate or corrupt records, even when a
prior run already wrote them — the destination system's idempotent
upsert (HTTP PATCH against an alternate key) is the guarantee, not a
read-then-decide check in this codebase. See CLAUDE.md Architectural
Directive 2.

Assertions on the logged summary read real stdout (``capsys``), not
``caplog``: ``BaseSyncRunner.run()`` calls ``configure_logging()``, which
replaces the root logger's handlers via ``logging.config.dictConfig``,
silently evicting pytest's ``caplog`` capture handler in the process.
"""

import re
from typing import Callable

import pytest
import responses
from runners.dataverse import DataverseInventorySyncRunner
from sources import CsvInventorySource

pytestmark = pytest.mark.acceptance

UPSERT_URL_PATTERN = re.compile(
    r".*/lagsol_inventoryitems\(lagsol_skuid='.*'\)$"
)


@responses.activate
def test_new_records_are_reported_as_created(
    dataverse_runner_factory: Callable[..., DataverseInventorySyncRunner],
    csv_source: CsvInventorySource,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A run against an empty destination reports every record as created."""
    responses.add(responses.PATCH, UPSERT_URL_PATTERN, status=201)

    exit_code = dataverse_runner_factory(csv_source).run()

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "3 created, 0 updated, 0 failed, 0 skipped (of 3 records)" in output


@responses.activate
def test_existing_records_are_updated_not_duplicated(
    dataverse_runner_factory: Callable[..., DataverseInventorySyncRunner],
    csv_source: CsvInventorySource,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A run against a destination with these records reports updates."""
    responses.add(responses.PATCH, UPSERT_URL_PATTERN, status=204)

    exit_code = dataverse_runner_factory(csv_source).run()

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "0 created, 3 updated, 0 failed, 0 skipped (of 3 records)" in output


@responses.activate
def test_sync_never_performs_a_check_then_act_loop(
    dataverse_runner_factory: Callable[..., DataverseInventorySyncRunner],
    csv_source: CsvInventorySource,
) -> None:
    """Every write is a PATCH; the sync never issues a GET before writing.

    This is the literal architectural guarantee: idempotency comes from
    the HTTP verb semantics of the upsert itself, not from application
    code reading a record first to decide whether to create or update.
    """
    responses.add(responses.PATCH, UPSERT_URL_PATTERN, status=201)

    dataverse_runner_factory(csv_source).run()

    methods_used = {call.request.method for call in responses.calls}
    assert methods_used == {"PATCH"}


@responses.activate
def test_rerunning_the_same_feed_converges_to_all_updates(
    dataverse_runner_factory: Callable[..., DataverseInventorySyncRunner],
    csv_source: CsvInventorySource,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Running the same feed twice reports the second run as all updates."""
    responses.add(responses.PATCH, UPSERT_URL_PATTERN, status=201)
    first_exit_code = dataverse_runner_factory(csv_source).run()
    assert first_exit_code == 0
    first_output = capsys.readouterr().out
    assert (
        "3 created, 0 updated, 0 failed, 0 skipped (of 3 records)"
        in first_output
    )

    responses.reset()
    responses.calls.reset()

    responses.add(responses.PATCH, UPSERT_URL_PATTERN, status=204)
    second_exit_code = dataverse_runner_factory(csv_source).run()

    assert second_exit_code == 0
    second_output = capsys.readouterr().out
    assert (
        "0 created, 3 updated, 0 failed, 0 skipped (of 3 records)"
        in second_output
    )
