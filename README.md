# Linear Analytics Group - Dataverse OData Sync Engine

A Python service that migrates ERP inventory data into Microsoft Dataverse via
the OData Web API, utilizing an extensible, multi-layer architecture designed
to readily adopt alternative enterprise destination systems.

**[Full documentation index →](docs/README.md)**

## Highlights

- **Idempotent by construction** — every write is an `HTTP PATCH` against
  a Dataverse alternate key; re-running a sync after a partial failure
  never creates a duplicate or corrupt record.
- **Independently variable architecture** — source format, write
  protocol, and destination system each vary on their own axis (mixin
  composition, protocol inheritance, or constructor injection, matched
  to the shape of the variation), so a new destination or service is
  additive, not a rewrite. See [Architecture Deep-Dive](docs/architecture.md).
- **Structural typing over inheritance, even for test doubles** —
  `typing.Protocol` throughout, so transport clients, source
  implementations, and Key Vault clients are typed against the
  behavior they use, not a concrete (often third-party) class. See
  [Protocols & Typing](docs/design-decisions/protocols-and-typing.md).
- **Secrets escalate from `.env` to Azure Key Vault** with zero code
  changes and no breaking path, provisioned via infrastructure-as-code.
  See [Configuration & Secrets](docs/design-decisions/configuration-and-secrets.md).
- **Structured JSON logging** — one self-describing JSON object per
  line, every contextual field independently queryable by a log
  aggregation platform (Azure Monitor, Datadog, ELK).
- **Bounded, resilient concurrency** — a `ThreadPoolExecutor` write
  pool, a consecutive-failure circuit breaker, and a memory-bounded
  in-flight futures window. See [Concurrency & Resilience](docs/design-decisions/concurrency-and-resilience.md).
- **Enforced quality bar, not just documented** — `mypy --strict`,
  `pydocstyle --convention=numpy`, and the full unit/integration/
  acceptance test suite run in CI on every push.
- **Zero-setup mock demo** — see the real production code path run in
  under a minute, no Azure account or network access required.

## The business problem

Inventory data lives in an ERP system as a flat, append-only feed. Microsoft
Dataverse — the system of record for downstream Power Platform apps — needs
that data kept in sync. This sync should be maintained without creating
duplicate records, without needing manual reconciliation, and without making
format assumptions related to the source or destination.

This solution solves three key problems:

1. **Sync inventory records into Dataverse idempotently.** The sync prevents
   record duplication, preventing the creation of duplicate or corrupt records,
   even when prior runs fail.
2. **Source and Destination Agnostic.** Modular architecture separates the
   service kit from the service — supporting various source and destination
   formats (e.g. CSV, JSON, Parquet) and solutions.
3. **Operable beyond simple execution.** Structured machine-parseable logs,
   validated configuration, and strict typing make failures diagnosable in
   production and support integration with external log solutions
   (e.g. Azure Monitor Log Analytics, Datadog, ELK Stack, etc.)

## Architecture

The repository is split into three layers, supporting separation of concerns.
Each layer holds a single responsibility and one-way dependency on the layer
below it. The full layer diagram is large — see it at full size in
[Architecture Deep-Dive](docs/architecture.md#layer-diagram); the table
below is the at-a-glance summary:

| Layer | Package | Owns | Must never contain |
|---|---|---|---|
| Transport | `shared/lag-data-utils` | HTTP mechanics (`BaseHttpClient` — pooling, timeout, retry-with-backoff), OData v4 CRUD (`ODataClient`), MSAL auth, Dataverse-specific headers, the `AuthenticationError` hierarchy | Environment reads, a config framework, business logic |
| Scaffolding | `shared/lag-service-kit` | Settings base classes, structured logging, input-format readers (including chunked CSV reading), generic dedup (whole-DataFrame and chunked), a generic `ConsecutiveFailureCircuitBreaker`, the source- and destination-agnostic `BaseSyncRunner` orchestration algorithm (generic over the transport client type), the OData v4 write-protocol base `BaseODataSyncRunner` (concurrent upsert loop + circuit breaker, reusable by any OData destination), and the `RecordSource`/`ChunkedRecordSource` source-composition protocols | Dataverse-specific, inventory-specific, or source-format-specific knowledge; any baked-in default number tuned to one service (see `defaults.py`) |
| Orchestration | `services/inventory-sync-engine` | Two independent things that combine, never duplicate: the domain mixin `InventoryDomainMixin` (dedup, source binding, inventory-domain-specific) and one destination leaf class per target system (`DataverseInventorySyncRunner`, combining the mixin with `lag_service_kit`'s shared write-protocol base) — plus, on a wholly separate axis, one `RecordSource` implementation per feed format (`CsvInventorySource`, the only one that also satisfies the optional `ChunkedRecordSource` capability, and `JsonInventorySource`), composed into a runner by the caller. `defaults.py` holds every constructor default tuned to this service specifically | Anything reusable by a service that isn't this one |

For the full rationale — why three layers, why mixins vs. inheritance
vs. composition for each axis, and how a second destination or service
would be added — see [Architecture Deep-Dive](docs/architecture.md).
For a full sequence diagram of one sync run, see
[Execution Flow](docs/execution-flow.md).

## Quick start

See the engine run in under a minute, no Azure account or network
access required:

```bash
cd services/inventory-sync-engine
python3 run_mock_sync.py
```

This runs the real `DataverseInventorySyncRunner`/`BaseSyncRunner`
production code path — dedup, the circuit breaker, structured JSON
logging, the idempotent-upsert loop — against a shipped mock feed,
with a fake Entra ID/Dataverse layer standing in only for network
calls. It exits `1` on purpose, simulating a realistic mixed outcome
to demonstrate per-record failure isolation — not a broken demo.

For a full setup against a real Dataverse environment (Entra ID app
registration, `.env` configuration, Azure Key Vault), and for how this
repository verifies itself (mypy, pydocstyle, pytest, CI), see
[Local Environment Setup](docs/setup.md).

## Documentation

| Topic | Doc |
|---|---|
| Architecture rationale | [Architecture Deep-Dive](docs/architecture.md) |
| Execution flow (sequence diagram) | [Execution Flow](docs/execution-flow.md) |
| Configuration & secrets (Key Vault) | [Configuration & Secrets](docs/design-decisions/configuration-and-secrets.md) |
| Data pipeline (readers, validation, field mapping) | [Data Pipeline](docs/design-decisions/data-pipeline.md) |
| Protocols & structural typing | [Protocols & Typing](docs/design-decisions/protocols-and-typing.md) |
| Concurrency & resilience | [Concurrency & Resilience](docs/design-decisions/concurrency-and-resilience.md) |
| Packaging & dependency pinning | [Packaging & Dependencies](docs/design-decisions/packaging-and-dependencies.md) |
| Power Platform solution | [Power Platform Solution](docs/power-platform.md) |
| Repository layout | [Repository Layout](docs/repository-layout.md) |
| Full local setup + CI verification | [Local Environment Setup](docs/setup.md) |
| Governance (branching, commits, QA gates) | [Governance](docs/GOVERNANCE.md) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for commit conventions, quality
gates, and review requirements; see [Governance](docs/GOVERNANCE.md)
for the full repository policy.

## License

This repository is proprietary, source-available for evaluation only
— see the root [LICENSE](LICENSE) file.
