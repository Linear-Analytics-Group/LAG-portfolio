← [Back to README](../../README.md) · [All docs](../README.md)

# Design Decisions: Data Pipeline

How format-agnostic ingestion works, why pre-flight validation runs
before dedup rather than deep inside it, and why field mapping is a
constructor-injected dict instead of an external mapping file.

## Table of Contents

- [`RecordReader` and `RecordSource` — Format-Agnostic Ingestion](#recordreader-and-recordsource--format-agnostic-ingestion)
- [Ingest Validation: Fail Fast on a Malformed Feed, Not Deep in Dedup](#ingest-validation-fail-fast-on-a-malformed-feed-not-deep-in-dedup)
- [Field Mapping: Constructor-Injected Dict vs. External Mapping File](#field-mapping-constructor-injected-dict-vs-external-mapping-file)

## `RecordReader` and `RecordSource` — Format-Agnostic Ingestion

Two protocols cooperate here, at two different layers, both living in
`lag_service_kit` since neither carries any domain-specific knowledge:

```python
# lag_service_kit.readers — generic: any file format into a DataFrame
class RecordReader(Protocol):
    def load(self, path: Path) -> pd.DataFrame: ...

# lag_service_kit.sources — generic: a runner's source-composition contract
class RecordSource(Protocol):
    def read_records(self) -> pd.DataFrame: ...
```

`lag_service_kit.readers` ships three `RecordReader` implementations —
`CsvRecordReader`, `JsonRecordReader` (expects `orient="records"` JSON),
and `ParquetRecordReader` — generic across any service. The inventory
service ships two sources today, each wrapping one reader with the one
thing it adds — knowing *which* file: `sources/csv.py:CsvInventorySource`
wraps `CsvRecordReader` over `data/erp_mock_inventory_data_feed.csv`, and
`sources/json.py:JsonInventorySource` wraps `JsonRecordReader` over
`data/erp_mock_inventory_data_feed.json` — the same mock inventory
dataset, shipped in both formats. Both `read_records()` implementations
satisfy `RecordSource` identically.

Crucially, `InventoryDomainMixin` depends on `RecordSource`, not
any concrete source class, and receives one through its constructor
rather than through inheritance:

```python
class InventoryDomainMixin:
    def __init__(self, source: RecordSource) -> None:
        self.source = source

    def load_records(self) -> pd.DataFrame:
        return dedupe_last_seen(self.source.read_records(), key=self.dedupe_key)
```

(Simplified for this point: the real `load_records()` first checks
whether `source` also satisfies the optional `ChunkedRecordSource`
capability — see [Protocols & Typing](protocols-and-typing.md) — and
reads/dedupes in bounded-memory chunks when it does, falling back to
the single-shot call shown here otherwise.)

Supporting a further format (Parquet, a REST feed) means adding one more
sibling module implementing only `read_records()` with the matching
`RecordReader`. No runner changes, because no runner inherits from a
source: `DataverseInventorySyncRunner(source=JsonInventorySource())`
reads JSON with the exact same class used for CSV — run against the two
mock feeds, both sources produce identical deduplicated records.
`InventoryDomainMixin.load_records()` (dedup) and
`BaseODataSyncRunner.sync_records()` (the upsert loop) never
change either way — both only ever depend on the resulting `DataFrame`,
never the source that produced it.

## Ingest Validation: Fail Fast on a Malformed Feed, Not Deep in Dedup

Without validation, a column missing from a malformed feed surfaces
as a raw `KeyError` inside `pandas.DataFrame.drop_duplicates` or an
`AttributeError` inside `itertuples()`, several calls away from
where the real problem lies — a blank business key from the source
flowing straight through dedup and into a destination write as a
literal alternate-key value.

**Pre-flight validation:** `lag_service_kit.validation` adds two
small, generic checks — `require_columns` (every named column
exists) and `require_non_null` (a given column has no null/blank
value) — plus `RecordValidationError`, the exception type they
raise. `InventoryDomainMixin.load_records()` calls both, via a
private `_validate()` helper, immediately after reading and before
dedup, for both the plain and chunked read paths (a malformed chunk
fails before the *next* chunk is even pulled from the source, not
only after every chunk has already been read). Required columns are
constructor injected (`required_columns`, defaulting to
`defaults.DEFAULT_REQUIRED_COLUMNS`), matching this repo's standing
"Constructor Injection vs. Environment Bloat" pattern (see
[Configuration & Secrets](configuration-and-secrets.md)) rather than a
hardcoded list.

**Where the exception type lives, and why:** `RecordValidationError`
is defined in `lag_service_kit` (generic scaffolding), not in the
inventory service, even though only the inventory service raises it
today. This mirrors `AuthenticationError`'s placement in the generic
transport layer (`lag_data_utils`) rather than a Dataverse-specific
module: it lets `lag_service_kit.runners.base.BaseSyncRunner.run()`
catch it — alongside `pydantic.ValidationError` and
`AuthenticationError`, logged as "Data validation error" rather than
falling into `run()`'s generic "unexpected error" branch — without
`lag_service_kit` importing anything inventory-specific to do so. A
second service built later could raise the same exception type for
its own validation rules and get the same treatment for free; that's
a byproduct of where the class lives, not something wired up for a
second service today.

**Deliberately not built:** validating business-rule semantics (e.g.,
is `unit_price` non-negative, does it look like a real currency
value) rather than structural shape (columns present, key non-null)
is a full schema-validation framework's job (e.g., `pandera`,
`great_expectations`) — building one for a three-column schema with
one destination would be the same premature abstraction this repo
already declined for field mapping (see below); the two checks here
cover the failure modes that turn into an opaque crash or a corrupted
alternate key, not every possible data-quality rule a real deployment
might eventually want.

## Field Mapping: Constructor-Injected Dict vs. External Mapping File

Typically, enterprise-integration field mapping is achieved through a
**metadata-driven, declarative mapping specification** — a YAML/JSON
mapping document (or a mapping-UI that generates one), loaded and
applied by a generic mapper at runtime. This approach lets
non-engineers audit mappings, supports several customers' mappings off
one deployed codebase, and enables tooling (schema-drift detection,
mapping editors) that's impossible once a mapping is buried in a
method body.

We deliberately did **not** build that here:

* **Scope Mismatch:** A full external mapping-file loader solves a
  multi-tenant problem. This portfolio has one destination and a
  three-column schema — building a generic mapping-config engine for
  that would be premature abstraction with no current payoff.
* **Consistency With an Existing, Documented Decision:** This codebase
  already chose Constructor Injection over `.env`-driven configuration
  specifically so schema-affecting changes go through code review and a
  deployment pipeline (see [Configuration & Secrets](configuration-and-secrets.md)).
  A live-editable external mapping file without code review
  requires safeguards beyond this project's current scope designed to
  prevent inadvertent or silent data corruption in the destination system.
* **Preventing the use of Data as Code:**
  When data is set in code *as an unstructured method body* rather than as
  *data*, it's opaque to review, impossible to reuse generically,
  and requires a full method override to change it.

**Constructor Injection:** `build_payload()` applies a
constructor-injected `field_mapping: Dict[str, str]` (source column ->
Dataverse field, defaulting to `DEFAULT_FIELD_MAPPING`) generically,
via one dict comprehension. This approach stands up the mapping as
data supplied at construction time, providing the flexibility needed
to support varied Dataverse entities while the mapping itself still
ships in code and goes through the same PR review as other schema
changes.

Scalability to support simultaneous mappings from a single deployment
may require a shift to declarative-file configuration, provided that
framework provides the necessary guardrails to prevent data corruption.

---

← [Back to README](../../README.md) · [All docs](../README.md)
