← [Back to README](../README.md)

# Local Environment Setup

Full setup against a real Dataverse environment, the zero-setup mock
demo, and how this repository verifies itself (mypy, pydocstyle,
pytest, CI). For the fastest way to see the engine run, jump straight
to [Zero-Setup Mock Execution](#zero-setup-mock-execution).

## Table of Contents

- [Full Setup](#full-setup)
- [Zero-Setup Mock Execution](#zero-setup-mock-execution)
- [Verification](#verification)

## Full Setup

**Prerequisites:** Python 3.13+, a Dataverse environment with an
application user registered for the target Entra ID app — *unless*
you just want to see the engine run: see
[Zero-Setup Mock Execution](#zero-setup-mock-execution) below, which
needs neither.

1. **Create and activate a virtual environment** at the repo root:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Editable-install both shared packages**, then the service's own
   dependencies:

   ```bash
   pip install -e ./shared/lag-data-utils
   pip install -e ./shared/lag-service-kit
   pip install -r services/inventory-sync-engine/requirements.txt
   ```

   `requirements.txt` is an exactly-pinned, hash-verified lock file,
   not a loose requirements list — see
   [Dependency Pinning](design-decisions/packaging-and-dependencies.md#dependency-pinning-loose-for-libraries-locked-for-the-application)
   for why, and how to regenerate it after a version bump.

   Editable installs mean `from lag_data_utils.clients.dataverse import
   DataverseClient` and `from lag_service_kit.settings import
   BaseServiceSettings` resolve straight to `shared/*/src/`, so edits to
   either shared package take effect immediately, with no reinstall and no
   `sys.path` manipulation.

   Running the test suite or the [Verification](#verification) checks
   below needs the root `pyproject.toml`'s optional dependency groups —
   these are not needed when simply running the service itself. The
   root project has no module content of its own — there's nothing to
   iterate on, so unlike the two shared packages above, a plain
   (non-editable) install is all this needs; this exists only to
   resolve the `dev`/`test` extras:

   ```bash
   pip install ".[dev,test]"   # pytest, responses, mypy, pydocstyle, coverage
   ```

   CI (`.github/workflows/ci.yml`) deliberately does **not** use
   editable installs for the two shared packages either — it builds a
   real wheel for each (`python -m build --wheel`) and installs that,
   so CI validates the actual artifact a release would ship, not a
   source-tree reference that can hide packaging bugs (e.g., a
   `[tool.hatch.build]` misconfiguration silently excluding a file from
   the real wheel). Editable installs remain the right choice here, in
   local dev, specifically because the goal is different: fast
   iteration on shared-package code, not artifact validation.

3. **Configure credentials.** Copy `.env.example` to `.env` at the repo
   root and fill in your Dataverse environment's values:

   ```bash
   cp .env.example .env
   ```

   | Variable | Required | Purpose |
   |---|---|---|
   | `AZURE_TENANT_ID` | Yes | Entra ID tenant GUID |
   | `AZURE_CLIENT_ID` | Yes | Registered app's client ID |
   | `AZURE_CLIENT_SECRET` | Yes | Registered app's client secret |
   | `DATAVERSE_URL` | Yes | Root URL, e.g. `https://org.crm.dynamics.com` |
   | `LOG_LEVEL` | No (default `INFO`) | Root logging level |
   | `AZURE_KEY_VAULT_URL` | No (default unset) | Optional Azure Key Vault URL — when set, the four values above are resolved from Key Vault instead; see [Secrets Management](design-decisions/configuration-and-secrets.md#secrets-management-azure-key-vault-vs-plain-env) |

   `InventorySyncSettings` finds this file automatically by walking up from
   `config.py`'s own location — run the service from any working
   directory and it still resolves.

4. **Run the sync**:

   ```bash
   cd services/inventory-sync-engine
   python3 dataverse_sync_runner.py
   ```

   A healthy run logs a single JSON line and exits `0`:

   ```json
   {"timestamp": "2026-07-22T10:07:26-0400", "level": "INFO", "logger": "lag_service_kit.runners.base", "message": "Sync complete: 0 created, 100 updated, 0 failed (of 100 records).", "records_created": 0, "records_updated": 100, "records_failed": 0, "total_records": 100}
   ```

   Missing configuration, a rejected credential, or a per-record HTTP
   failure all log at `ERROR` and exit `1` — nothing is ever silently
   swallowed.

## Zero-Setup Mock Execution

Full setup steps above need a real Dataverse environment and Entra ID
app registration. To see the engine run without either:

```bash
cd services/inventory-sync-engine
python3 run_mock_sync.py
```

No `.env` file, no Azure credentials, and no network access at all —
`run_mock_sync.py` runs the real
`DataverseInventorySyncRunner`/`BaseSyncRunner` orchestration against
the shipped mock CSV feed, with a fake Entra ID/Dataverse layer
standing in for just the two things a real environment would
otherwise provide: MSAL token acquisition and the destination's HTTP
responses. Every other piece — dedup, the circuit breaker, the JSON
structured logging, the idempotent-upsert loop — is the exact,
unmodified production code path; nothing about how the engine
actually runs is different from a real sync.

The fake HTTP layer deterministically simulates a realistic mixed
outcome — about 38% created, 60% updated, and 2% a transient failure
— so the exit code is `1`, on purpose: this demonstrates the engine's
per-record failure isolation and structured error logging (see
[Circuit Breaker vs. Unconditional Retry Exhaustion](design-decisions/concurrency-and-resilience.md#circuit-breaker-vs-unconditional-retry-exhaustion)),
not a broken demo. The ~2% simulated failure rate is a deliberate,
checked choice — comfortably below the circuit breaker's default
`failure_threshold` of 5 in absolute count, and since the breaker
only trips on *consecutive* failures, a couple of failures scattered
at random across ~100 records can never form a run of 5 in a row, so
this demo can never trip it, regardless of dispatch order (see
`tests/acceptance/test_mock_sync_demo.py`).

For confirming a specific *real* Entra ID app registration and
Dataverse environment are configured correctly — as opposed to seeing
the engine run at all — see `test_connection.py`, the real-environment
counterpart: same `InventorySyncSettings`/`DataverseClient` wiring,
but requires a filled-in `.env` and real network access.

## Verification

This repository holds itself to a strict bar (see `CLAUDE.md`'s
Architectural Directives): every module under `shared/` and
`services/inventory-sync-engine/` — `config.py`, `defaults.py`,
`dataverse_sync_runner.py`, `runners/`, and `sources/` — passes both
mypy and pydocstyle scans with zero findings, and so does the entire
`tests/` suite under mypy. `generate_mock_data.py` is the one deliberate
exception — a standalone dev/test data generator excluded via
`[tool.mypy]`'s `exclude` in `pyproject.toml`, not part of the
delivered service.

`pyproject.toml`'s `[tool.mypy]` section carries `--strict`,
`--ignore-missing-imports`, the `pydantic.mypy` plugin (needed for
`pydantic-settings`' `BaseSettings` field-sourcing semantics), and the
`generate_mock_data.py` exclusion, so running plain `mypy` picks up the
same configuration as CI:

```bash
mypy <files>
pydocstyle --convention=numpy <files>
```

This is mechanically enforced, not just documented: `.github/workflows/ci.yml`
runs mypy, pydocstyle, and the full `tests/` suite on every push and pull
request against `trunk`, from a clean checkout — see that workflow for
the exact commands. CI also installs the `pac` CLI as a `dotnet` global
tool and packs the Dataverse solution
(`pac solution pack --folder platform/power-platform/LAGInventorySync/src
--packagetype Unmanaged`) on every run — the same command documented in
[Power Platform Solution](power-platform.md), gated in CI rather than only
runnable by hand, so a malformed schema change fails the build instead of
surfacing only when someone next tries to pack it. The same root `pyproject.toml` also declares this
repo's own dev/test tooling (`mypy`, `pydocstyle`, `pytest`, `responses`,
etc.) as `[project.optional-dependencies]` extras (`pip install
".[dev,test]"`) rather than separate `requirements-*.txt` files — the
modern, PEP 621-aligned way to declare tooling dependencies, and what CI
itself installs from.

Both `lag-data-utils` and `lag-service-kit` ship a
`py.typed` marker (PEP 561) so a consumer running `mypy --strict` against
just a service file still gets full type information instead
of silently degrading to `Any`.

---

← [Back to README](../README.md)
