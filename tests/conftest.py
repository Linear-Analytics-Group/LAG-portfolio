"""Shared fixtures for the centralized test suite.

Available to every test in ``tests/``, regardless of layer. Nothing here
depends on process environment variables or a real ``.env`` file being
present or absent — every fixture that needs Dataverse credentials or
Azure identity fabricates fake ones.
"""

from pathlib import Path
from typing import Any, Callable, List

import pandas as pd
import pytest
from lag_data_utils.clients.dataverse import DataverseClient
from runners.dataverse import DataverseInventorySyncRunner
from sources import CsvInventorySource, JsonInventorySource

#: Every environment variable a Dataverse-backed service's settings read.
DATAVERSE_ENV_VARS: List[str] = [
    "AZURE_TENANT_ID",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "DATAVERSE_URL",
    "LOG_LEVEL",
]

FAKE_ENVIRONMENT_URL: str = "https://faketestorg.crm.dynamics.com"
FAKE_BEARER_TOKEN: str = "fake-test-bearer-token"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Clear every Dataverse/Azure/service environment variable for this test.

    Guarantees settings tests are hermetic regardless of what the host
    machine's real shell environment happens to have set.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest fixture used to clear environment variables for the
        duration of one test.

    Returns
    -------
    pytest.MonkeyPatch
        The same fixture, for tests that also want to set specific
        variables afterward.
    """
    for var in DATAVERSE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def dataverse_client(monkeypatch: pytest.MonkeyPatch) -> DataverseClient:
    """Build a ``DataverseClient`` wired to a fake environment.

    ``msal.ConfidentialClientApplication.__init__`` performs a real network
    call (OIDC tenant discovery) before any token is ever requested, so
    the fake has to replace the MSAL application class itself, not just
    ``acquire_bearer_token`` — patching the method would be too late,
    since construction has already tried to reach the network by then.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Used to replace ``msal.ConfidentialClientApplication`` so no real
        MSAL/Entra ID network call is ever attempted, at construction or
        at token-acquisition time.

    Returns
    -------
    DataverseClient
        A client whose ``base_url`` is
        ``FAKE_ENVIRONMENT_URL + "/api/data/v9.2"`` and whose real,
        unmodified ``acquire_bearer_token()`` returns
        ``FAKE_BEARER_TOKEN`` by exercising the real cache-miss code
        path against the fake MSAL application.
    """

    class _FakeConfidentialClientApplication:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def acquire_token_silent(
            self, *args: object, **kwargs: object
        ) -> None:
            return None

        def acquire_token_for_client(
            self, *args: object, **kwargs: object
        ) -> dict:  # type: ignore[type-arg]
            return {"access_token": FAKE_BEARER_TOKEN}

    monkeypatch.setattr(
        "msal.ConfidentialClientApplication",
        _FakeConfidentialClientApplication,
    )
    return DataverseClient(
        tenant_id="fake-tenant-id",
        client_id="fake-client-id",
        client_secret="fake-client-secret",
        environment_url=FAKE_ENVIRONMENT_URL,
    )


@pytest.fixture
def raw_inventory_records() -> pd.DataFrame:
    """Build a small, deliberately-duplicated raw inventory feed.

    Used by dedup/sync tests.

    Returns
    -------
    pd.DataFrame
        Four rows with ``sku_id``, ``item_name``, ``unit_price`` columns.
        ``SKU-002`` appears twice, simulating an append-only feed's delta
        update — the later row should win after dedup, leaving 3 unique
        records.
    """
    return pd.DataFrame(
        [
            {"sku_id": "SKU-001", "item_name": "Widget", "unit_price": 9.99},
            {"sku_id": "SKU-002", "item_name": "Gadget", "unit_price": 19.99},
            {
                "sku_id": "SKU-002",
                "item_name": "Gadget (updated)",
                "unit_price": 24.99,
            },
            {"sku_id": "SKU-003", "item_name": "Gizmo", "unit_price": 4.50},
        ]
    )


@pytest.fixture
def csv_source(
    tmp_path: Path, raw_inventory_records: pd.DataFrame
) -> CsvInventorySource:
    """Build a ``CsvInventorySource`` backed by a temp file.

    Parameters
    ----------
    tmp_path : Path
        Pytest's per-test temporary directory.
    raw_inventory_records : pd.DataFrame
        The sample feed to write to the temp CSV file.

    Returns
    -------
    CsvInventorySource
        A source reading the temp CSV file, not the shipped mock feed.
    """
    csv_path = tmp_path / "mock_feed.csv"
    raw_inventory_records.to_csv(csv_path, index=False)
    return CsvInventorySource(csv_path=csv_path)


@pytest.fixture
def json_source(
    tmp_path: Path, raw_inventory_records: pd.DataFrame
) -> JsonInventorySource:
    """Build a ``JsonInventorySource`` backed by a temp file.

    Parameters
    ----------
    tmp_path : Path
        Pytest's per-test temporary directory.
    raw_inventory_records : pd.DataFrame
        The sample feed to write to the temp JSON file.

    Returns
    -------
    JsonInventorySource
        A source reading the temp JSON file, not the shipped mock feed.
    """
    json_path = tmp_path / "mock_feed.json"
    raw_inventory_records.to_json(json_path, orient="records")
    return JsonInventorySource(json_path=json_path)


@pytest.fixture
def dataverse_runner_factory(
    monkeypatch: pytest.MonkeyPatch, dataverse_client: DataverseClient
) -> Callable[..., DataverseInventorySyncRunner]:
    """Return a factory building a runner wired to a fake environment.

    Bypasses real settings loading and real client construction entirely
    (``load_settings``/``build_client`` are monkeypatched on the instance),
    so the only thing exercised over the network boundary is the mocked
    HTTP traffic a test itself registers via ``responses``.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Used to stub ``load_settings`` and ``build_client`` on each
        constructed runner instance.
    dataverse_client : DataverseClient
        The fake-environment client every constructed runner will use.

    Returns
    -------
    Callable[..., DataverseInventorySyncRunner]
        A callable taking a ``source`` (satisfying ``InventorySource``)
        plus any other ``DataverseInventorySyncRunner`` constructor
        keyword argument (e.g. ``failure_threshold``, ``max_workers``),
        returning a ready-to-``.run()`` ``DataverseInventorySyncRunner``.
    """
    from types import SimpleNamespace

    def _build(source: object, **kwargs: Any) -> DataverseInventorySyncRunner:
        runner = DataverseInventorySyncRunner(
            source=source, **kwargs  # type: ignore[arg-type]
        )
        monkeypatch.setattr(
            runner,
            "load_settings",
            lambda: SimpleNamespace(log_level="DEBUG"),
        )
        monkeypatch.setattr(
            runner, "build_client", lambda settings: dataverse_client
        )
        return runner

    return _build
