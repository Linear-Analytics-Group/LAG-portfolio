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
│       ├── requirements.txt
│       ├── config.py                     # InventorySyncSettings — composes shared settings mixins
│       ├── dataverse_sync_runner.py      # Entrypoint only — pairs a leaf runner with a source, then .run()
│       ├── runners/                      # Domain + write-protocol axes — combined via multiple inheritance
│       │   ├── __init__.py               # Exports InventoryDomainMixin, BaseODataInventorySyncRunner
│       │   ├── base.py                   # InventoryDomainMixin — dedupe + source binding (no client type)
│       │   ├── odata.py                  # BaseODataInventorySyncRunner[ODataClient] — the upsert loop
│       │   └── dataverse.py              # DataverseInventorySyncRunner — the only Dataverse-specific code
│       └── sources/                      # Source-format axis — composed into a runner, never inherited
│           ├── __init__.py               # Exports InventorySource, CsvInventorySource, JsonInventorySource
│           ├── base.py                   # InventorySource protocol
│           ├── csv.py                    # CsvInventorySource — the only CSV-specific code
│           └── json.py                   # JsonInventorySource — the only JSON-specific code
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
                ├── readers/              # RecordReader protocol + Csv/Json/Parquet implementations
                └── runners/
                    └── base.py           # BaseSyncRunner[ClientT] — generic over the transport client type
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
     to that service (e.g., the `entity_set`, `alternate_key_field`, and
     `build_payload()` hooks in `runners/dataverse.py:DataverseInventorySyncRunner`).
     A service's own code should be the thinnest layer; if a class or
     function has no service-specific knowledge in it, it belongs in
     `lag-service-kit` instead — see Directive 4 for how a service's own
     `runners/` and `sources/` packages are themselves expected to be
     internally layered.

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
4. **Match the layering technique to the shape of the variation.** Not
   every axis a service must support is a hierarchy, and forcing an axis
   that varies *independently* of another into a single inheritance
   chain produces either a combinatorial explosion of classes (one per
   source-format × destination pairing) or an incorrect, permanent
   coupling (a destination that can only ever read one feed format).
   `services/inventory-sync-engine/runners/` and `sources/` are the
   reference implementation of the standing pattern — apply this same
   three-part shape whenever a service must support more than one
   destination, wire protocol, or source format:

   - **Single inheritance, for axes that are genuinely hierarchical.**
     Increasing protocol specificity is a real hierarchy: `BaseClient` →
     `ODataClient` → `DataverseClient` in `shared/lag-data-utils/clients`,
     and, in lock step, `lag_service_kit.runners.base.BaseSyncRunner[ClientT]`
     → a protocol-specific base (e.g. `runners/odata.py:BaseODataInventorySyncRunner(BaseSyncRunner[ODataClient])`)
     for the write loop against that protocol. `BaseSyncRunner` is generic
     over `ClientT` (bound to `BaseClient`) precisely so every class in
     one of these chains agrees on a single client type — narrowing it
     independently at each level is a Liskov substitution violation and
     an `mypy --strict` error.
   - **Mixin composition (multiple inheritance), for axes that vary
     independently and are class-level, structural concerns.** Domain
     knowledge (what a record *is*, how to dedupe it) and write-protocol
     mechanics (how a record is upserted) vary independently of each
     other and must each be defined exactly once: a domain mixin (e.g.
     `runners/base.py:InventoryDomainMixin`, which does not itself
     inherit `BaseSyncRunner` or commit to any `ClientT`) combines with a
     protocol-specific base via multiple inheritance in the destination
     leaf class — e.g.
     `class DataverseInventorySyncRunner(InventoryDomainMixin, BaseODataInventorySyncRunner)`.
     A future SAP/Salesforce destination on the same OData protocol
     writes a sibling leaf combining the same two bases; a future
     destination on a different wire protocol (SOAP, a bulk-upload REST
     API) writes a sibling protocol base and still inherits the same
     domain mixin unchanged. Neither base ever duplicates the other's
     logic, and neither axis multiplies against the other.

     When a protocol base needs one piece of domain-supplied data —
     e.g. `BaseODataInventorySyncRunner.sync_records()` needs a record's
     business-key column name to log and to pass to `upsert_record()` —
     declare it as a bare, unassigned annotation on the protocol base
     (`dedupe_key: str`, no default), and let the domain mixin be the
     only class that ever assigns it (`InventoryDomainMixin.dedupe_key: str = "sku_id"`).
     This is a contract, not a duplication: `mypy --strict` type-checks
     the attribute access on the protocol base, but there is exactly one
     place in the codebase where its value is ever set. Never give the
     protocol base its own default for a domain-owned attribute — that
     would silently fork the value across the two axes the moment either
     side changed independently.
   - **Constructor injection (composition, not inheritance), for
     per-run operational choices.** Which source feed a given run reads
     is not a property of the destination class — it varies
     independently, at runtime, from what the destination class is. A
     domain mixin's constructor takes a source collaborator satisfying a
     `typing.Protocol` (e.g. `sources/base.py:InventorySource`, supplying
     `read_records() -> pd.DataFrame`) and the entrypoint pairs a leaf
     class with a concrete source instance
     (`DataverseInventorySyncRunner(source=CsvInventorySource())` in
     `dataverse_sync_runner.py`). A destination class must never inherit
     from a source-specific class — that would fix it to one feed format
     forever. `sources/csv.py:CsvInventorySource` and
     `sources/json.py:JsonInventorySource` ship today as siblings, each
     implementing only `read_records()`; a future format (e.g.
     `sources/parquet.py:ParquetInventorySource`) is added the same way.
     Every existing destination leaf can be pointed at any of them
     immediately, with no new subclass.

   Default to this three-part shape when adding a new destination, wire
   protocol, source format, or service — modularity and scalability take
   precedence over the shortest path to a working single-destination
   implementation.

## Dataverse Environment Reference

- **Target environment:** a Microsoft Dataverse environment reachable at
  `https://<your-org>.crm.dynamics.com/` — the real URL lives only in the
  git-ignored `.env` (`DATAVERSE_URL`), never in this file or in source.
- **Auth identity:** an Entra ID application (service principal)
  registered against that environment — its tenant ID, client ID, and
  client secret live only in the git-ignored `.env`
  (`AZURE_TENANT_ID`/`AZURE_CLIENT_ID`/`AZURE_CLIENT_SECRET`), never in
  this file or in source.
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
- **Public remote (`origin`):** GitHub — public, live as of Phase 4 below.

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
- [X] **Phase 4 — Git Cleanliness & Public Push**
  - Ran `git status` — confirmed `.env`, local databases, scratch files, and
    raw config states are excluded from tracking (see `.gitignore`).
  - Committed the full `runners`/`sources` mixin-composition refactor and
    documentation fixes as a series of scoped conventional commits, rather
    than one squashed `feat(sync-engine): ...` commit, so each change is
    independently reviewable and revertible.
  - Merged `dev-diagram` into `trunk` on GitHub (PR #3) and confirmed
    `origin/trunk` reflects it.
  - Ran the `gpsync` double-vault push: `trunk` is now identical
    (same commit) across the local working tree, `origin` (GitHub), and
    `cloud` (Google Drive bare mirror).

