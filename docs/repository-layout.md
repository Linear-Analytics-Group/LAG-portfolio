← [Back to README](../README.md)

# Repository Layout

```text
LAG-portfolio/
├── .env                                    # Local secrets — git-ignored, see .env.example
├── .env.example                            # Template for the 6 variables config.py reads
├── pyproject.toml                          # [tool.mypy], [tool.pytest.ini_options], and the [project]/
│                                            # [project.optional-dependencies] "dev"/"test" extras — this
│                                            # repo's own dev/test tooling, never published (see below)
├── platform/
│   └── power-platform/
│       └── LAGInventorySync/                # Configuration-as-Code Dataverse solution manifest
│           └── src/Entities/                 # lagsol_InventoryItem schema, alternate keys
│
├── services/
│   └── inventory-sync-engine/
│       ├── config.py                        # InventorySyncSettings
│       ├── dataverse_sync_runner.py         # Entrypoint — main() instantiates a leaf runner
│       ├── defaults.py                      # DEDUPE_KEY, DEFAULT_MAX_WORKERS, DEFAULT_CHUNK_SIZE,
│       │                                    # DEFAULT_WRITE_WINDOW_SIZE, DEFAULT_FAILURE_THRESHOLD,
│       │                                    # DEFAULT_REQUIRED_COLUMNS — this service's tuned numbers
│       ├── runners/                          # Domain axis — the protocol axis lives in lag_service_kit
│       │   ├── __init__.py                   # Exports InventoryDomainMixin
│       │   ├── base.py                       # InventoryDomainMixin — dedupe, composes a source (no client type)
│       │   └── dataverse.py                  # DataverseInventorySyncRunner — the only Dataverse-specific code
│       ├── sources/                          # Source axis — composed into a runner, never inherited
│       │   ├── __init__.py                   # Exports CsvInventorySource, JsonInventorySource
│       │   ├── csv.py                        # CsvInventorySource — the only source that streams in chunks
│       │   └── json.py                       # JsonInventorySource — the only JSON-specific code
│       ├── requirements.txt
│       ├── run_mock_sync.py                 # Zero-setup demo entrypoint — no .env, no Azure, no network
│       ├── test_connection.py               # Real-environment connectivity smoke test — needs a filled .env
│       ├── generate_mock_data.py            # Dev/test mock feed generator — git-ignored, excluded from mypy
│       └── data/
│           ├── erp_mock_inventory_data_feed.csv
│           └── erp_mock_inventory_data_feed.json
│
├── shared/
│   ├── lag-data-utils/                     # Transport clients
│   │   └── src/lag_data_utils/clients/
│   │       ├── base.py                      # BaseClient, AuthenticationError — auth contract + error root
│   │       ├── http.py                      # BaseHttpClient — pooled session, timeout, retry-with-backoff
│   │       ├── odata.py                     # ODataClient — generic OData v4 CRUD
│   │       └── dataverse.py                 # DataverseClient + from_settings() + Protocol
│   │
│   └── lag-service-kit/                    # Cross-service scaffolding
│       └── src/lag_service_kit/
│           ├── settings.py                  # BaseServiceSettings, find_repo_env_file()
│           ├── dataverse_settings.py        # DataverseConnectionSettings mixin
│           ├── azure_key_vault.py            # AzureKeyVaultSettingsSource — optional Key Vault-backed fields
│           ├── validation.py                 # RecordValidationError, require_columns(), require_non_null()
│           ├── logging.py                   # configure_logging(), JsonFormatter
│           ├── dedupe.py                     # dedupe_last_seen(), dedupe_last_seen_chunks()
│           ├── circuit_breaker.py            # ConsecutiveFailureCircuitBreaker — any batch write loop
│           ├── readers/                      # RecordReader, Csv (+ chunked)/Json/Parquet
│           ├── sources/                      # RecordSource, ChunkedRecordSource — source-composition contract
│           │   ├── __init__.py               # Exports RecordSource, ChunkedRecordSource
│           │   └── base.py
│           └── runners/
│               ├── __init__.py               # Exports BaseSyncRunner, BaseODataSyncRunner
│               ├── base.py                   # BaseSyncRunner[ClientT] — destination-agnostic orchestration
│               └── odata.py                  # BaseODataSyncRunner — concurrent upsert loop + breaker
│
└── tests/                                   # Centralized suite, layered to mirror the source tree
    ├── conftest.py                           # Shared fixtures — fake Entra ID/Dataverse, no real network
    ├── unit/
    │   ├── lag_data_utils/                   # BaseClient, BaseHttpClient, ODataClient, DataverseClient
    │   ├── lag_service_kit/                  # settings, dedupe, logging, readers, circuit breaker,
    │   │                                     # BaseSyncRunner, BaseODataSyncRunner
    │   └── inventory_sync_engine/            # InventoryDomainMixin,
    │                                          # DataverseInventorySyncRunner, CsvInventorySource
    ├── integration/                          # Real classes across a mocked network boundary
    └── acceptance/                           # Black-box: idempotency, operability, source/dest agnosticism,
                                                # circuit breaker, zero-setup mock demo — one requirement each
```

---

← [Back to README](../README.md)
