# LAG Dataverse OData Sync Engine

A Python service that migrates ERP inventory data into Microsoft Dataverse
via the OData Web API, built as a reusable foundation for future
Dataverse-backed integrations rather than a single-purpose script.

## The business problem

Inventory data lives in an ERP system as a flat, append-only feed. Microsoft
Dataverse — the system of record for downstream Power Platform apps — needs
that data kept in sync without ever creating duplicate records, without a
human reconciling the two systems by hand, and without assuming any single
input format or destination will be the last one this organization ever
needs.

Concretely, this repository solves three problems at once:

1. **Sync inventory records into Dataverse idempotently.** Re-running the
   sync must never create duplicates or corrupt existing records, even if
   the previous run crashed halfway through.
2. **Do it without hardcoding today's shape of the problem.** Today the
   source is a CSV and the destination is Dataverse. Neither is guaranteed
   to stay that way, so the parts of the solution that aren't specific to
   *inventory* or *Dataverse* are built to outlive both.
3. **Make it operable, not just runnable.** Structured logs, validated
   configuration, and strict typing so failures are diagnosable in
   production, not just on someone's laptop.

## Architecture

The repository is split into three layers, each with a single
responsibility and a one-way dependency on the layer below it:

```mermaid
graph TD
    subgraph "services/inventory-sync-engine — orchestration"
        SR["sync_runner.py<br/>main() + sync_inventory_records()"]
        CFG["config.py<br/>InventorySyncSettings"]
    end

    subgraph "shared/lag-service-kit — cross-service scaffolding"
        BSS["settings.py<br/>BaseServiceSettings, find_repo_env_file()"]
        DCS["dataverse_settings.py<br/>DataverseConnectionSettings"]
        LOG["logging.py<br/>configure_logging()"]
        RDR["readers/<br/>RecordReader protocol · Csv · Json · Parquet"]
        DEDUPE["dedupe.py<br/>dedupe_last_seen()"]
    end

    subgraph "shared/lag-data-utils — transport clients"
        BASE["base.py<br/>BaseClient"]
        ODATA["odata.py<br/>ODataClient"]
        DV["dataverse.py<br/>DataverseClient"]
    end

    CFG -->|inherits| BSS
    CFG -->|inherits| DCS
    SR --> CFG
    SR --> LOG
    SR --> RDR
    SR --> DEDUPE
    SR --> DV
    DV --> ODATA --> BASE
    DV -.->|"from_settings() accepts anything<br/>matching the Protocol"| DCS
```

| Layer | Package | Owns | Must never contain |
|---|---|---|---|
| Transport | `shared/lag-data-utils` | HTTP/OData mechanics, MSAL auth, Dataverse-specific headers | Environment reads, a config framework, business logic |
| Scaffolding | `shared/lag-service-kit` | Settings base classes, structured logging, input-format readers, generic dedup | Dataverse-specific or inventory-specific knowledge |
| Orchestration | `services/inventory-sync-engine` | Wiring, column mappings, the one function that knows what an inventory record is | Anything reusable by a service that isn't this one |

### Why three layers, not two

The obvious split is "library vs. application" — transport code in
`lag-data-utils`, everything else in the service. That's what this repo
started with. It breaks down the moment you imagine a *second* service:
config loading, logging setup, and "read this file format into a
DataFrame" would either get copy-pasted into every new service, or bolted
onto `lag-data-utils` until it stopped being a clean transport layer.

`lag-service-kit` exists to hold exactly the code that is reusable across
*any* future service but isn't a transport concern — and to do that without
making the transport layer depend on a specific configuration framework.
Concretely:

- `lag-data-utils` has zero dependency on Pydantic or any settings library.
  `DataverseClient.from_settings()` is typed against a structural
  `typing.Protocol` (`DataverseConnectionSettings` in `dataverse.py`) —
  any object exposing the right four attributes works, regardless of what
  produced it. Today that's a Pydantic model from `lag-service-kit`;
  tomorrow it could be anything.
- `lag-service-kit` depends on Pydantic and pandas, but knows nothing about
  Dataverse alternate keys or inventory columns — a service that talks to
  a different destination system, or ingests a different kind of record,
  reuses it unchanged.
- The service itself should be the thinnest layer. In
  `sync_runner.py`, `sync_inventory_records()` is the *only* function that
  knows what an inventory record looks like (`sku_id`, `item_name`,
  `unit_price`, the `lagsol_inventoryitems` entity set). Everything else in
  that file is wiring into the two shared packages.

## Key design patterns

### Settings composition via mixins

`InventorySyncSettings` (in `services/inventory-sync-engine/config.py`)
adds no fields of its own — it composes two `lag-service-kit` mixins:

```python
class InventorySyncSettings(DataverseConnectionSettings, BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file=find_repo_env_file(Path(__file__)),
        ...
    )
```

- `DataverseConnectionSettings` — `azure_tenant_id`, `azure_client_id`,
  `azure_client_secret`, `dataverse_url`, with whitespace- and
  trailing-slash-stripping validators. Any future service that talks to
  Dataverse mixes this in rather than redeclaring the same four fields.
- `BaseServiceSettings` — `log_level`, shared by every service regardless
  of destination system.
- `find_repo_env_file(Path(__file__))` walks upward from the calling
  module looking for a `.env` file, mirroring `python-dotenv`'s discovery
  behavior — a service finds its repo-root `.env` without hardcoding how
  many directories separate it from that root.

Missing or empty required fields raise `pydantic.ValidationError` with a
field-by-field report, caught once in `main()` and logged.

### `from_settings()` and structural typing

`lag-data-utils` needs four string attributes to construct a
`DataverseClient`. Rather than importing a concrete settings class (which
would chain the transport layer to Pydantic) or duplicating a builder
function in every service, `DataverseClient` exposes:

```python
@classmethod
def from_settings(cls, settings: DataverseConnectionSettings) -> "DataverseClient":
    ...
```

where `DataverseConnectionSettings` is a `@runtime_checkable
typing.Protocol` — not a Pydantic base class. Any object with the right
shape satisfies it. This is verified directly: a `lag_service_kit`
settings instance passes `isinstance(obj, Proto)` against the
`lag_data_utils` protocol despite the two packages never importing from
each other.

### `RecordReader` — format-agnostic ingestion

`lag_service_kit.readers` defines one protocol:

```python
class RecordReader(Protocol):
    def load(self, path: Path) -> pd.DataFrame: ...
```

with three implementations shipped today — `CsvRecordReader`,
`JsonRecordReader` (expects `orient="records"` JSON), and
`ParquetRecordReader`. The inventory sync engine uses `CsvRecordReader`
because that's what the ERP feed happens to be today; swapping to JSON or
Parquet is a one-line change in `sync_runner.py`, not a rewrite. Business
logic downstream of a reader (`dedupe_last_seen`, `sync_inventory_records`)
only ever depends on the resulting `DataFrame`, never on the source format.

## Execution flow

```mermaid
sequenceDiagram
    participant Runner as sync_runner.main()
    participant Settings as InventorySyncSettings
    participant Client as DataverseClient
    participant Entra as Microsoft Entra ID
    participant Reader as CsvRecordReader
    participant Dedupe as dedupe_last_seen()
    participant Dataverse as Dataverse Web API (v9.2)

    Runner->>Settings: InventorySyncSettings()
    alt required field missing/empty
        Settings-->>Runner: ValidationError
        Runner->>Runner: log + exit 1
    end
    Settings-->>Runner: validated config

    Runner->>Client: DataverseClient.from_settings(settings)
    Runner->>Client: acquire_bearer_token()
    Client->>Entra: OAuth2 client-credentials grant (MSAL)
    alt credentials rejected
        Entra-->>Client: AADSTS error
        Client-->>Runner: DataverseAuthenticationError
        Runner->>Runner: log + exit 1
    end
    Entra-->>Client: Bearer token (cached for reuse)

    Runner->>Reader: load(CSV_PATH)
    Reader-->>Runner: raw DataFrame (sku_id, item_name, unit_price)
    Runner->>Dedupe: dedupe_last_seen(df, key="sku_id")
    Dedupe-->>Runner: one row per sku_id (last-seen wins)

    loop each deduplicated record
        Runner->>Client: upsert_record(entity_set="lagsol_inventoryitems",<br/>alternate_key_name="lagsol_skuid", key_value=sku_id, payload)
        Client->>Dataverse: HTTP PATCH /lagsol_inventoryitems(lagsol_skuid='...')
        alt record didn't exist
            Dataverse-->>Client: 201 Created
        else record existed
            Dataverse-->>Client: 204 No Content
        else request rejected
            Dataverse-->>Client: 4xx/5xx
            Client-->>Runner: requests.HTTPError (logged, counted, loop continues)
        end
    end

    Runner->>Runner: log created/updated/failed tally, exit 0 or 1
```

Re-running the sync is safe by construction: `upsert_record` issues an
`HTTP PATCH` against the `lagsol_skuid` alternate key, which is itself the
idempotency guarantee (OData v4 upsert semantics) — there is no
read-then-decide step that a second run could race against.

## Repository layout

```text
LAG-portfolio/
├── .env                                    # Local secrets — git-ignored, see .env.example
├── platform/
│   └── power-platform/
│       └── LAGInventorySync/                # Configuration-as-Code Dataverse solution manifest
│           └── src/Entities/                 # lagsol_InventoryItem schema, alternate keys
│
├── services/
│   └── inventory-sync-engine/
│       ├── config.py                        # InventorySyncSettings
│       ├── sync_runner.py                   # Orchestration + sync_inventory_records()
│       ├── generate_mock_data.py            # Mock ERP feed generator (dev/test only)
│       ├── test_connection.py               # Standalone MSAL/Dataverse smoke test
│       ├── requirements.txt
│       └── data/erp_mock_inventory_data_feed.csv
│
└── shared/
    ├── lag-data-utils/                      # Transport clients
    │   └── src/lag_data_utils/clients/
    │       ├── base.py                       # BaseClient — auth contract only
    │       ├── odata.py                      # ODataClient — generic OData v4 CRUD
    │       └── dataverse.py                  # DataverseClient + from_settings() + Protocol
    │
    └── lag-service-kit/                     # Cross-service scaffolding
        └── src/lag_service_kit/
            ├── settings.py                   # BaseServiceSettings, find_repo_env_file()
            ├── dataverse_settings.py         # DataverseConnectionSettings mixin
            ├── logging.py                    # configure_logging()
            ├── dedupe.py                      # dedupe_last_seen()
            └── readers/                       # RecordReader, Csv/Json/Parquet
```

## Local environment setup

**Prerequisites:** Python 3.11+, a Dataverse environment with an
application user registered for the target Entra ID app.

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

   Editable installs mean `from lag_data_utils.clients.dataverse import
   DataverseClient` and `from lag_service_kit.settings import
   BaseServiceSettings` resolve straight to `shared/*/src/`, so edits to
   either shared package take effect immediately, with no reinstall and no
   `sys.path` manipulation.

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

   `InventorySyncSettings` finds this file automatically by walking up from
   `config.py`'s own location — run the service from any working
   directory and it still resolves.

4. **Run the sync**:

   ```bash
   cd services/inventory-sync-engine
   python3 sync_runner.py
   ```

   A healthy run logs a single structured line and exits `0`:

   ```text
   2026-07-08T20:40:38-0400 | INFO     | __main__ | Sync complete: 0 created, 100 updated, 0 failed (of 100 records).
   ```

   Missing configuration, a rejected credential, or a per-record HTTP
   failure all log at `ERROR` and exit `1` — nothing is ever silently
   swallowed.

### Verification

This repository holds itself to a strict bar (see `CLAUDE.md`'s
Architectural Directives): every module under `shared/` and
`services/inventory-sync-engine/config.py`/`sync_runner.py` passes both

```bash
mypy --strict --ignore-missing-imports <files>
pydocstyle --convention=numpy <files>
```

with zero findings. Both `lag-data-utils` and `lag-service-kit` ship a
`py.typed` marker (PEP 561) so a consumer running `mypy --strict` against
just a service file — not the whole monorepo at once — still gets full
type information instead of silently degrading to `Any`.

## Project status

Tracked against a phased public-release roadmap in `CLAUDE.md`. As of this
document: dynamic execution and schema verification (Phase 1) and the
production refactor to Pydantic settings, structured logging, NumPy
docstrings, and strict typing (Phase 2) are both complete and verified
end-to-end against the live Dataverse environment.
