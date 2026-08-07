← [Back to README](../README.md)

# Documentation Index

Deep-dive documentation for the Dataverse OData Sync Engine. The root
[README](../README.md) covers the business problem, the architecture
diagram, and how to run the zero-setup mock demo; the pages below hold
the full rationale behind each design decision.

## Architecture

- [Architecture Deep-Dive](architecture.md) — the three-layer split,
  why each axis of variation (source format, write protocol,
  destination system) uses a different composition technique, and how
  a second destination or service would be added.
- [Execution Flow](execution-flow.md) — a full sequence diagram of one
  sync run, from `main()` to exit code.
- [Repository Layout](repository-layout.md) — the full annotated file
  tree.

## Design Decisions

- [Configuration & Secrets](design-decisions/configuration-and-secrets.md)
  — settings composition via mixins, constructor injection vs. `.env`,
  Azure Key Vault, and format-level config validation.
- [Data Pipeline](design-decisions/data-pipeline.md) — `RecordReader`/
  `RecordSource`, ingest validation, and field mapping.
- [Protocols & Typing](design-decisions/protocols-and-typing.md) —
  `from_settings()` and structural typing, Protocols over inheritance
  (including test doubles), and runtime-checkable Protocols.
- [Concurrency & Resilience](design-decisions/concurrency-and-resilience.md)
  — multi-threading vs. OData `$batch`, the circuit breaker, and the
  write-path memory bound.
- [Packaging & Dependencies](design-decisions/packaging-and-dependencies.md)
  — monorepo dependency resolution, dependency pinning, and packaging
  governance.

## Platform & Operations

- [Power Platform Solution](power-platform.md) — the
  Configuration-as-Code Dataverse schema and `pac` CLI toolchain.
- [Local Environment Setup](setup.md) — full setup against a real
  Dataverse environment, the zero-setup mock demo, and this repo's
  verification/CI bar.

---

← [Back to README](../README.md)
