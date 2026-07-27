# Test suite

Centralized, top-down test suite for the whole repository — `shared/lag-data-utils`,
`shared/lag-service-kit`, and `services/inventory-sync-engine` all get their
coverage here, in one place, rather than each package shipping its own
`tests/` directory. This repo is developed and shipped as one integrated
system, not as independently distributed libraries, so the test suite
mirrors that: one suite, one `pytest` invocation, run from the repo root.

## Running the suite

```bash
pip install -r requirements-test.txt
pip install -e ./shared/lag-data-utils
pip install -e ./shared/lag-service-kit
pip install -r services/inventory-sync-engine/requirements.txt
pytest
```

No network access, no live Dataverse environment, and no `.env` file are
required — every HTTP call is mocked (`responses`), and settings tests
control their own environment variables explicitly.

## Top-down: three layers, run in order

The suite is organized by *how directly a test proves something the
business cares about*, not by which source file it happens to touch —
top-down, starting from the business requirements in the root `README.md`
and drilling into implementation detail only as needed:

```
tests/
├── acceptance/    # 1. Does this satisfy the stated business requirements?
├── integration/   # 2. Do the real classes wire together correctly?
└── unit/          # 3. Does this one class/function do the right thing in isolation?
```

Run top-down when investigating a failure, and when deciding how much to
test before shipping a change:

```bash
pytest -m acceptance    # run first — if these pass, the business requirements hold
pytest -m integration   # run next if you need to localize *where* in the wiring something broke
pytest -m unit          # drill in further to the exact class/function at fault
```

If `acceptance` passes, you have direct evidence the system does what
`README.md` claims it does — you don't need to inspect `integration` or
`unit` results to trust that. If `acceptance` fails, `integration` and
`unit` are where you find out *why*, without re-reading the acceptance
test itself.

### `acceptance/` — one file per business requirement

Each file maps directly to one of the three problems `README.md`'s
"business problem" section states this project solves:

| Requirement (`README.md`) | Test file |
|---|---|
| Sync inventory records into Dataverse idempotently | `test_idempotent_sync.py` |
| Source and destination agnostic | `test_source_destination_agnostic.py` |
| Operable beyond simple execution (structured logs, validated config, resilient to per-record failure) | `test_operability.py` |

These are black-box tests: they exercise `DataverseInventorySyncRunner`
through its public `.run()` entrypoint (or, where `.run()` would require
mocking away the very thing under test, through `.load_records()`), with
the HTTP boundary mocked via `responses` and MSAL token acquisition
patched. They do not reach into private methods.

### `integration/` — real classes, mocked network boundary

Tests here still use the real, concrete classes (`DataverseClient`,
`DataverseInventorySyncRunner`, `InventorySyncSettings`, ...) wired
together exactly as production does, but verify the *wiring* itself —
e.g., that `DataverseClient.from_settings()` really does accept an
`InventorySyncSettings` instance via structural typing, or that
`BaseSyncRunner.run()`'s fixed sequence really does call each hook in the
right order with the right arguments. Failures here point at a specific
seam between two components.

### `unit/` — one class or function, real collaborators replaced

Mirrors the `src`/service layout so a failing unit test points straight
at the file that needs fixing:

```
unit/
├── lag_data_utils/           # BaseClient, ODataClient, DataverseClient
├── lag_service_kit/          # dedupe, readers, settings, logging,
│                             # BaseSyncRunner, BaseODataSyncRunner
└── inventory_sync_engine/    # InventoryDomainMixin,
                               # DataverseInventorySyncRunner, CsvInventorySource, JsonInventorySource
```

## Fixtures

Shared fixtures live in `conftest.py` at the root of `tests/` (available
to every test) and in each layer's own `conftest.py` where a fixture is
only meaningful at that layer (e.g., a fully-wired mock Dataverse
environment is an `acceptance`/`integration` concern, not a `unit` one).
No test depends on process environment variables or a real `.env` file
being absent or present — settings tests set exactly the environment
variables they need via `monkeypatch` and clean up automatically.
