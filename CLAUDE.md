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
│       └── sync_runner.py                # Application entrypoint & orchestrator [ACTIVE WORK FRONT]
│
└── shared/
    └── lag-data-utils/                   # Distributable utility library layer [STABILIZED]
        ├── pyproject.toml                # PEP 517/660 build config (Hatchling backend)
        └── src/
            └── lag_data_utils/
                ├── __init__.py
                └── clients/
                    ├── __init__.py
                    ├── base.py           # Abstract root — authentication contract only
                    ├── odata.py          # Abstract OData v4 client (generic CRUD, protocol-only)
                    └── dataverse.py      # Concrete Dataverse client (MSAL auth + Dataverse headers)
```

`lag-data-utils` is installed into `.venv` as an editable package
(`pip install -e ./shared/lag-data-utils`), so imports resolve as
`from lag_data_utils.clients.dataverse import DataverseClient` — no path
manipulation hacks.

## Architectural Directives (Enforced)

These constraints govern all code generation, refactoring, and documentation
in this repo. They are not advisory.

1. **Maintain architectural separation.** Database transport clients live in
   `shared/lag-data-utils`. Execution orchestration, column mappings, and
   ingestion targets live in `services/inventory-sync-engine`. Never combine
   these layers in a single file.
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

- [X] **Phase 1 — Dynamic Execution & Schema Verification** *(current)*
  - Run `python3 sync_runner.py` from `services/inventory-sync-engine/` —
    confirm namespace bindings, editable install paths, and `.env` lookups
    all resolve without error.
  - Reconcile OData field casing in `sync_runner.py` payloads against literal
    logical names in the Power Apps Maker Portal.
  - Validate idempotency: run the sync script twice — second run must return
    `204 No Content`, not a constraint violation or duplicate record error.
- [ ] **Phase 2 — Production Code Refactoring**
  - Add pydantic and pydantic-settings to our runtime dependency array.
  - Implement a unified configuration schema (config.py) to replace all instance variables of load_dotenv().
  - Replace all stdout print() statements with a properly configured, structured Python logging matrix.
  - Standardize NumPy-style docstrings across `clients/base.py`,
    `clients/odata.py`, `clients/dataverse.py`, and `sync_runner.py`.
  - Inject strict type annotations across all execution paths in those three
    files.
- [ ] **Phase 3 — Public-Facing Documentation (`README.md`)**
  - Draft root `README.md`: business problem solved, architectural rationale
    for the transport/application layer split, local environment
    bootstrapping guide.
  - Embed a Mermaid sequence diagram: `Local CSV → Pandas deduplication
    filter → MSAL client credential handshake → Idempotent Dataverse OData
    PATCH (Alternate Key)`.
- [ ] **Phase 4 — Git Cleanliness & Public Push**
  - Run `git status` — confirm `.env`, local databases, scratch files, and
    raw config states are excluded from tracking.
  - Commit with conventional syntax:
    `feat(sync-engine): finalized modular provider validation and enterprise documentation`
  - Run `gpsync` (double-vault push).
