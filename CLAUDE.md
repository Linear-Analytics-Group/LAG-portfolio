# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Repository Purpose

`LAG-portfolio` is the Dataverse OData Sync Engine — a Python service that
migrates ERP inventory data into Microsoft Dataverse via the OData Web API.
It is a working codebase, not a documentation repo.

## Directory Structure

```text
LAG-portfolio/
├── .env                                  # Local vars only — Git ignored
├── .gitignore                            # Multi-layer isolation (excludes secrets, .venv)
│
├── platform/
│   └── power-platform/
│       └── LAGInventorySync/             # Configuration-as-Code Dataverse solution manifest
│           └── src/Entities/             # Deconstructed XML table schemas & alternate keys
│
├── services/
│   └── inventory-sync-engine/            # Standalone application layer
│       ├── data/
│       │   └── erp_mock_inventory_data_feed.csv  # Mock ERP source data stream
│       ├── generate_mock_data.py         # Mock ERP feed generator (dev/test only)
│       ├── test_connection.py            # Standalone MSAL/Dataverse connectivity smoke test
│       ├── requirements.txt
│       ├── config.py                     # InventorySyncSettings — composes shared settings mixins
│       └── dataverse_sync_runner.py                # Orchestration + sync_inventory_records (the only
│                                          # service-specific logic) [ACTIVE WORK FRONT]
│
└── shared/
    ├── lag-data-utils/                   # Transport client layer [STABILIZED]
    │   ├── pyproject.toml                # PEP 517/660 build config (Hatchling backend)
    │   └── src/
    │       └── lag_data_utils/
    │           ├── __init__.py
    │           └── clients/
    │               ├── __init__.py
    │               ├── base.py           # Abstract root — authentication contract only
    │               ├── odata.py          # Abstract OData v4 client (generic CRUD, protocol-only)
    │               └── dataverse.py      # Concrete Dataverse client (MSAL auth + Dataverse
    │                                     # headers) + DataverseConnectionSettings Protocol +
    │                                     # DataverseClient.from_settings() alternate constructor
    │
    └── lag-service-kit/                  # Cross-service scaffolding layer
        ├── pyproject.toml
        └── src/
            └── lag_service_kit/
                ├── __init__.py
                ├── settings.py           # BaseServiceSettings (log_level) + find_repo_env_file()
                ├── dataverse_settings.py # DataverseConnectionSettings Pydantic mixin
                ├── logging.py            # configure_logging() — structured logging matrix
                ├── dedupe.py             # dedupe_last_seen() — last-write-wins by key column
                └── readers/              # RecordReader protocol + Csv/Json/Parquet implementations
```

Both `shared/` packages are installed into `.venv` as editable packages
(`pip install -e ./shared/lag-data-utils`, `pip install -e ./shared/lag-service-kit`),
so imports resolve as `from lag_data_utils.clients.dataverse import DataverseClient`
and `from lag_service_kit.settings import BaseServiceSettings` — no path
manipulation hacks.

## Architectural Directives (Enforced)

These constraints govern all code generation, refactoring, and documentation
in this repo. They are not advisory.

1. **Maintain architectural separation.** Three layers, never combined in a
   single file:
   - `shared/lag-data-utils` — database transport clients only. No
     environment reads, no config framework, no business logic.
   - `shared/lag-service-kit` — cross-service scaffolding any current or
     future service needs regardless of destination system: Pydantic
     settings base classes, structured logging setup, input-format readers
     (CSV/JSON/Parquet), generic dedup utilities. No Dataverse- or
     inventory-specific knowledge.
   - `services/<service-name>` — execution orchestration, column mappings,
     ingestion targets, and whatever business logic is genuinely specific
     to that service (e.g., `sync_inventory_records` in `dataverse_sync_runner.py`).
     A service's own code should be the thinnest layer; if a function has
     no service-specific knowledge in it, it belongs in `lag-service-kit`
     instead.

   `lag-data-utils` stays free of any configuration-framework dependency
   (currently Pydantic) so it can be reused regardless of how a service
   manages its config: concrete clients expose a `from_settings()`
   alternate constructor typed against a structural `typing.Protocol`
   (see `DataverseConnectionSettings` in `dataverse.py`) rather than
   importing a concrete settings class from `lag-service-kit`.

   Within `clients/`, the transport hierarchy builds strictly on
   specificity — `BaseClient` → `ODataClient` → `DataverseClient`. Generic
   OData v4 protocol mechanics (CRUD verbs, `$filter`/`$select`/`$top`
   query options, alternate-key URL construction) belong in `odata.py` and
   must stay Dataverse-agnostic; this is what lets a future OData-compliant
   client (e.g., an SAP S/4HANA connector) subclass `ODataClient` directly
   instead of `DataverseClient`. Dataverse-specific concerns — MSAL/Entra ID
   auth, the `/api/data/v9.2` endpoint, the `Prefer: return=representation`
   header — belong only in `dataverse.py`.
2. **Enforce absolute idempotency.** All Dataverse write operations must use
   `HTTP PATCH` targeting system Alternate Keys directly. "Check-then-act"
   transactional loops (read record → decide → write) are rejected — the API
   verb itself is the idempotency guarantee.
3. **Appellate-ready documentation standard.** Docstrings and inline comments
   must pass a strict technical audit bar: explicit `Parameters`, `Returns`,
   and `Raises` sections (NumPy-style). No qualitative filler, no emotional
   framing — technical benchmarks and verifiable API states only.
4. **Extend the layering pattern beyond the transport clients.** The
   base-class-to-specific-subclass shape established in
   `shared/lag-data-utils/clients` (`BaseClient` → `ODataClient` →
   `DataverseClient`) is the standing pattern for this repository, not a
   one-off. Apply it at every layer where a service must support more than
   one destination, source format, or record shape: a destination-agnostic
   base class owns the shared orchestration/algorithm, and solution-specific
   subclasses inherit it and override or add only what differs for that
   destination — e.g., a `BaseInventorySyncRunner` in `lag-service-kit`
   subclassed by `DataverseInventorySyncRunner` today, with future
   `SapInventorySyncRunner` / `SalesforceInventorySyncRunner` subclasses
   under `services/inventory-sync-engine/runners/`. Default to this shape
   when adding a new destination, source format, or service — modularity
   and scalability take precedence over the shortest path to a working
   single-destination implementation.

## Dataverse Environment Reference

- **Target environment:** `https://orgd2d50d9c.crm.dynamics.com/`
- **Auth identity:** `jeff@linearanalyticsgroup.com`
- **Auth pattern:** MSAL client credentials flow (application service
  principal) — no user delegation flows.
- **Toolchain:** `.NET 10 Core` via `pac` CLI, Python 3 with MSAL.
- **Schema casing:** Verify all OData entity/field names against the Power
  Apps Maker Portal at time of execution. Alternate Key logical names are
  case-sensitive (e.g., `lagsol_ExternalSKUID` is distinct from
  `lagsol_externalskuid`).

## Git Topology

This repo pushes to two remotes — always use the aliases, not a bare
`git push`, unless told otherwise:

```bash
alias gporigin="git push -u origin $(git branch --show-current)"  # GitHub (public target)
alias gpcloud="git push cloud $(git branch --show-current)"       # Google Drive bare remote (private mirror)
alias gpsync="gporigin && gpcloud"                                # Double-vault push
```

- **Active working tree:** local-only, no cloud sync agent (avoids file-lock
  races / metadata corruption from Drive or iCloud filesystem hooks).
- **Private cloud remote (`cloud`):** bare repo on Google Drive, bridges
  iMac / MacBook / iPad Pro (via Working Copy). Updates only on explicit push.
- **Public remote (`origin`):** GitHub — push pending Phase 4 below.

## Current Mobilization Status

Tracking against the public-release roadmap. Work top-down; do not start a
later phase until the one above it is checked off.

- [X] **Phase 1 — Dynamic Execution & Schema Verification**
  - Run `python3 dataverse_sync_runner.py` from `services/inventory-sync-engine/` —
    confirm namespace bindings, editable install paths, and `.env` lookups
    all resolve without error.
  - Reconcile OData field casing in `dataverse_sync_runner.py` payloads against literal
    logical names in the Power Apps Maker Portal.
  - Validate idempotency: run the sync script twice — second run must return
    `204 No Content`, not a constraint violation or duplicate record error.
- [X] **Phase 2 — Production Code Refactoring**
  - Add pydantic and pydantic-settings to our runtime dependency array.
  - Implement a unified configuration schema (config.py) to replace all instance variables of load_dotenv().
  - Replace all stdout print() statements with a properly configured, structured Python logging matrix.
  - Standardize NumPy-style docstrings across `clients/base.py`,
    `clients/odata.py`, `clients/dataverse.py`, and `dataverse_sync_runner.py`.
  - Inject strict type annotations across all execution paths in those three
    files.
- [X] **Phase 3 — Public-Facing Documentation (`README.md`)**
  - Draft root `README.md`: business problem solved; architectural rationale
    for the three-tier split — `lag-data-utils` (transport clients),
    `lag-service-kit` (cross-service scaffolding: config, logging, readers,
    dedup), `services/inventory-sync-engine` (orchestration + the one
    inventory-specific function) — and why scaffolding lives in its own
    package rather than growing either the transport layer or a single
    service; local environment bootstrapping guide covering both editable
    installs (`pip install -e ./shared/lag-data-utils`,
    `pip install -e ./shared/lag-service-kit`).
  - Document the settings composition pattern: `InventorySyncSettings`
    combines `DataverseConnectionSettings` + `BaseServiceSettings` from
    `lag-service-kit`, and `DataverseClient.from_settings()` accepts any
    object structurally matching a `typing.Protocol` — so `lag-data-utils`
    depends on no particular configuration framework.
  - Document the `RecordReader` protocol and that CSV/JSON/Parquet input is
    already supported today (`lag_service_kit.readers`), not just CSV —
    accurate scope, not aspirational.
  - Embed a Mermaid sequence diagram reflecting what's actually built:
    `Local CSV (CsvRecordReader) → dedupe_last_seen(key="sku_id") →
    DataverseClient.from_settings() + eager MSAL bearer-token acquisition →
    Idempotent Dataverse OData PATCH (Alternate Key)`.
- [ ] **Phase 4 — Git Cleanliness & Public Push** *(current)*
  - Run `git status` — confirm `.env`, local databases, scratch files, and
    raw config states are excluded from tracking.
  - Commit with conventional syntax:
    `feat(sync-engine): finalized modular provider validation and enterprise documentation`
  - Run `gpsync` (double-vault push).

