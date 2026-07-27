"""Business requirement: the engine is runnable with zero setup.

A technical reviewer must be able to clone this repository and run
run_mock_sync.py immediately — no .env file, no Azure credentials, no
network access — and see the real sync engine's structured JSON logs
stream by. This is the acceptance-level proof that claim holds; the
individual fakes it depends on are covered in isolation by
tests/unit/inventory_sync_engine/test_run_mock_sync.py.
"""

import json

import pytest
import run_mock_sync

pytestmark = pytest.mark.acceptance


def test_main_runs_to_completion_with_no_env_vars_set(
    clean_env: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() reaches sync completion with no real env vars set.

    clean_env clears the environment first — this is the concrete
    proof that no real .env file or credential is required at all.
    The exit code alone can't prove this: ``run()`` returns ``1`` both
    for an environment/config failure and for the demo's own harmless
    simulated per-record failures (see
    ``test_the_simulated_failure_rate_never_trips_the_circuit_breaker``
    below), so this asserts on the "Sync complete" log line itself,
    which only ever logs once every earlier error branch in ``run()``
    (config, auth, source, validation, unexpected) has been passed.
    """
    run_mock_sync.main()

    lines = capsys.readouterr().out.strip().splitlines()

    assert any('"message": "Sync complete' in line for line in lines)


def test_the_simulated_failure_rate_never_trips_the_circuit_breaker(
    clean_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The demo's own simulated failures stay under the breaker's threshold.

    Parses the final structured "Sync complete" log line and asserts
    records_failed is comfortably below the shipped
    DEFAULT_FAILURE_THRESHOLD (5) — proving the demo's ~2% simulated
    failure rate is a deliberately safe choice, not a coincidence, and
    that every record was actually attempted (none skipped).
    """
    from defaults import DEFAULT_FAILURE_THRESHOLD

    run_mock_sync.main()

    lines = capsys.readouterr().out.strip().splitlines()
    summary = json.loads(lines[-1])

    assert summary["records_failed"] < DEFAULT_FAILURE_THRESHOLD
    assert (
        summary["records_created"]
        + summary["records_updated"]
        + summary["records_failed"]
        == summary["total_records"]
    )
