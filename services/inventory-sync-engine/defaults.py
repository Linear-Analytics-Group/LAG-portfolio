"""Constructor-injected defaults for this service, deliberately not env-driven.

Every value here is a code-level default overridable via a constructor
argument, never an environment variable — see README.md's "Constructor
Injection vs. Environment Bloat" for why. Only defaults that are
domain-generic (meaningful regardless of destination system) belong
here; a destination-specific default (e.g. Dataverse's entity set and
alternate key field names) stays next to the one leaf class that owns
it — see ``runners.dataverse.DEFAULT_ENTITY_SET`` — so a future,
different destination never risks inheriting an unrelated schema.
"""

#: The source column uniquely identifying an inventory item. A customer
#: whose source feed names this column differently overrides it at
#: construction time (see ``runners.base.InventoryDomainMixin``).
DEDUPE_KEY: str = "sku_id"

#: Columns (besides ``DEDUPE_KEY``, always required separately) that
#: every inventory record must carry, regardless of source feed format
#: or destination system — this is what makes a row "an inventory
#: record" at all (see ``runners.base.InventoryDomainMixin.load_records()``).
#: A customer whose source feed uses different column names overrides
#: this at construction time, the same as ``DEDUPE_KEY``.
DEFAULT_REQUIRED_COLUMNS: tuple[str, ...] = ("item_name", "unit_price")

#: Worker threads used to sync records concurrently (see
#: ``lag_service_kit.runners.odata.BaseODataSyncRunner``, which takes
#: no default of its own for this — see its docstring). This workload
#: is I/O-bound (waiting on HTTP responses), so threads give real
#: parallelism despite the GIL. If you raise this, the destination
#: client's HTTP connection pool must be sized at least as large or
#: concurrency silently caps at the pool size instead — see
#: ``DataverseInventorySyncRunner.build_client()``, which derives the
#: client's pool size from this same value automatically.
DEFAULT_MAX_WORKERS: int = 10

#: Row count per chunk when reading from a source that supports chunked
#: reading (see ``lag_service_kit.sources.base.ChunkedRecordSource``).
#: Bounds ``InventoryDomainMixin.load_records()``'s memory use to
#: roughly one chunk plus one deduped row per unique ``dedupe_key``
#: value seen so far, rather than the entire source file at once.
#: 10,000 is a starting point, not a measured optimum for any
#: particular feed size — raise it for fewer, larger chunks (less read
#: overhead, more peak memory) or lower it for the opposite trade-off.
DEFAULT_CHUNK_SIZE: int = 10_000

#: Maximum upsert futures ``BaseODataSyncRunner.sync_records()`` holds
#: in memory at once, submitted but not yet collected (see its own
#: docstring, which takes no default of its own for this either).
#: Bounds the write path's memory the same way ``DEFAULT_CHUNK_SIZE``
#: bounds the read path's: rather than submitting one future per
#: deduplicated record up front regardless of total feed size, at most
#: this many are ever outstanding, with a completed one's result
#: collected and a new one submitted in its place. Must be at least
#: ``DEFAULT_MAX_WORKERS`` — fewer would leave a worker idle with
#: nothing queued — 5x is enough headroom above it that a worker
#: finishing one upsert almost always has its next one already
#: waiting, without ever holding the whole batch's futures at once.
DEFAULT_WRITE_WINDOW_SIZE: int = 50

#: Consecutive upsert failures that trip
#: ``BaseODataSyncRunner.sync_records()``'s circuit breaker (see
#: ``lag_service_kit.circuit_breaker.ConsecutiveFailureCircuitBreaker``),
#: skipping every record not yet attempted rather than continuing to
#: batter an already-failing destination for the rest of the run. Low
#: enough to react to a genuine, sustained outage within a handful of
#: calls; high enough that a few isolated bad records (a data quality
#: issue, not a systemic one) don't needlessly abort an otherwise-
#: healthy run. Not destination-specific, but tuned to this service's
#: own operational tolerance, not a universal constant — neither the
#: breaker class nor ``BaseODataSyncRunner.__init__`` takes a default
#: for this (see their own docstrings).
DEFAULT_FAILURE_THRESHOLD: int = 5
