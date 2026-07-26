"""Business requirement: stop battering a systemically failing destination.

A sustained run of consecutive failures (a real outage, not a few bad
records) must trip a circuit breaker and stop issuing further requests
for the rest of that run, rather than dispatching every remaining
record against an already-failing destination. Every write is an
idempotent alternate-key upsert, so a later, separate re-run after the
underlying issue is fixed reproduces the correct result at no extra
cost — there is nothing to "resume."
"""

import re
from pathlib import Path
from typing import Callable

import pandas as pd
import pytest
import responses
from runners.dataverse import DataverseInventorySyncRunner
from sources import CsvInventorySource

pytestmark = pytest.mark.acceptance

UPSERT_URL_PATTERN = re.compile(
    r".*/lagsol_inventoryitems\(lagsol_skuid='.*'\)$"
)

#: Comfortably larger than the default max_workers (10), so records
#: beyond the first worker-sized batch are still queued, not yet
#: started, when the breaker trips — the only records that can
#: actually be skipped without ever reaching the network.
RECORD_COUNT = 30
FAILURE_THRESHOLD = 3


@pytest.fixture
def large_csv_source(tmp_path: Path) -> CsvInventorySource:
    """A CSV source with RECORD_COUNT unique, never-duplicated SKUs."""
    rows = [
        {
            "sku_id": f"SKU-{i:03d}",
            "item_name": "Widget",
            "unit_price": 9.99,
        }
        for i in range(RECORD_COUNT)
    ]
    csv_path = tmp_path / "large_feed.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return CsvInventorySource(csv_path=csv_path)


@responses.activate
def test_a_sustained_outage_trips_the_breaker_and_skips_the_rest(
    dataverse_runner_factory: Callable[..., DataverseInventorySyncRunner],
    large_csv_source: CsvInventorySource,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every upsert failing trips the breaker before all 30 are attempted."""
    responses.add(responses.PATCH, UPSERT_URL_PATTERN, status=500)

    exit_code = dataverse_runner_factory(
        large_csv_source, failure_threshold=FAILURE_THRESHOLD
    ).run()

    output = capsys.readouterr().out
    assert exit_code == 1
    assert (
        f"Circuit breaker tripped after {FAILURE_THRESHOLD} consecutive "
        "failures" in output
    )
    assert len(responses.calls) < RECORD_COUNT


@responses.activate
def test_a_healthy_run_never_mentions_the_circuit_breaker(
    dataverse_runner_factory: Callable[..., DataverseInventorySyncRunner],
    large_csv_source: CsvInventorySource,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A fully successful run never trips the breaker or skips anything."""
    responses.add(responses.PATCH, UPSERT_URL_PATTERN, status=201)

    exit_code = dataverse_runner_factory(
        large_csv_source, failure_threshold=FAILURE_THRESHOLD
    ).run()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Circuit breaker" not in output
    assert f"{RECORD_COUNT} created, 0 updated, 0 failed" in output
    assert len(responses.calls) == RECORD_COUNT
