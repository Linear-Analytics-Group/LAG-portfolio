"""Unit tests for lag_service_kit.runners.odata.BaseODataSyncRunner.

Every test uses ``max_workers=1``, making execution strictly
sequential and every assertion deterministic — with more than one
worker, whether a given record's request is "in flight" or "not yet
started" when the breaker trips depends on scheduling, which is
exactly the nondeterminism a focused unit test should avoid. The
acceptance-level tests (in the inventory service) exercise the real,
concurrent default instead. This class is destination/domain-agnostic
scaffolding, tested here alongside the rest of ``lag_service_kit``
rather than in any one service — the stub below uses made-up field
names (``stub_items``/``stub_skuid``), not real inventory ones, to
keep that agnosticism honest.
"""

from typing import Any

import pandas as pd
import pytest
import requests
from lag_data_utils.clients.odata import ODataClient
from lag_service_kit.runners.odata import BaseODataSyncRunner

pytestmark = pytest.mark.unit


class _StubODataClient(ODataClient):
    """A real ODataClient subclass that fails a fixed number of calls.

    Overrides only ``upsert_record`` (to fake failures without a real
    network call) and the two abstract members every ``ODataClient``
    must supply. A genuine subclass, not a duck-typed stand-in, so it
    satisfies ``sync_records``'s ``client: ODataClient`` parameter with
    no ``# type: ignore`` needed — mirroring
    ``tests.unit.lag_data_utils.test_http_client._ConcreteHttpClient``.
    """

    def __init__(self, fail_count: int) -> None:
        super().__init__()
        self._fail_count = fail_count
        self.calls = 0

    @property
    def base_url(self) -> str:
        return "https://stub.example.com/api/data/v9.2"

    def acquire_bearer_token(self) -> str:
        return "stub-bearer-token"

    def upsert_record(
        self,
        entity_set: str,
        alternate_key_name: str,
        key_value: str,
        payload: dict[str, Any],
    ) -> requests.Response:
        self.calls += 1
        response = requests.Response()
        if self.calls <= self._fail_count:
            response.status_code = 500
            raise requests.HTTPError(response=response)
        response.status_code = 201
        return response


class _StubRunner(BaseODataSyncRunner):
    """The minimum concrete subclass needed to exercise sync_records()."""

    dedupe_key = "sku_id"

    @property
    def entity_set(self) -> str:
        return "stub_items"

    @property
    def alternate_key_field(self) -> str:
        return "stub_skuid"

    def build_payload(self, row: Any) -> dict[str, Any]:
        return {}

    def load_settings(self) -> Any:
        raise NotImplementedError

    def build_client(self, settings: Any) -> Any:
        raise NotImplementedError

    def load_records(self) -> pd.DataFrame:
        raise NotImplementedError


def _records(count: int) -> pd.DataFrame:
    # pandas-stubs types the DataFrame constructor as Any; the explicit
    # annotation asserts the real return type mypy --strict needs.
    records: pd.DataFrame = pd.DataFrame(
        [{"sku_id": f"SKU-{i}"} for i in range(count)]
    )
    return records


def test_sync_records_reports_all_created_when_nothing_fails() -> None:
    """A healthy run reports every record created, nothing skipped."""
    client = _StubODataClient(fail_count=0)
    runner = _StubRunner(max_workers=1, failure_threshold=2)

    result = runner.sync_records(client, _records(3))

    assert result == {"created": 3, "updated": 0, "failed": 0, "skipped": 0}
    assert client.calls == 3


def test_circuit_breaker_trips_and_skips_the_remaining_records() -> None:
    """After failure_threshold consecutive failures, the rest are skipped.

    With max_workers=1, records are attempted strictly in order, so
    this is fully deterministic: the first 2 calls fail and trip the
    breaker (threshold=2), and the remaining 3 are skipped without
    ever reaching the client.
    """
    client = _StubODataClient(fail_count=100)
    runner = _StubRunner(max_workers=1, failure_threshold=2)

    result = runner.sync_records(client, _records(5))

    assert result == {"created": 0, "updated": 0, "failed": 2, "skipped": 3}
    assert client.calls == 2


def test_a_success_before_the_threshold_prevents_tripping() -> None:
    """A success resets the streak, so the breaker never trips.

    fail_count=1 means only the first call fails; with a threshold of
    2, that lone failure is never followed by a second consecutive
    one, so every record after it is genuinely attempted.
    """
    client = _StubODataClient(fail_count=1)
    runner = _StubRunner(max_workers=1, failure_threshold=2)

    result = runner.sync_records(client, _records(4))

    assert result == {"created": 3, "updated": 0, "failed": 1, "skipped": 0}
    assert client.calls == 4


def test_failure_threshold_of_one_skips_after_a_single_failure() -> None:
    """A threshold of 1 trips on the very first failure."""
    client = _StubODataClient(fail_count=100)
    runner = _StubRunner(max_workers=1, failure_threshold=1)

    result = runner.sync_records(client, _records(4))

    assert result == {"created": 0, "updated": 0, "failed": 1, "skipped": 3}
    assert client.calls == 1
