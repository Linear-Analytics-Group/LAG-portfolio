← [Back to README](../../README.md) · [All docs](../README.md)

# Design Decisions: Concurrency & Resilience

Why the write path uses client-side multi-threading instead of OData
`$batch`, how the circuit breaker stops a sustained outage from being
dispatched against uselessly, and the memory bound placed on
in-flight write futures.

## Table of Contents

- [Multi-Threaded Concurrency vs. OData v4 `$batch`](#multi-threaded-concurrency-vs-odata-v4-batch)
- [Circuit Breaker vs. Unconditional Retry Exhaustion](#circuit-breaker-vs-unconditional-retry-exhaustion)
- [Resilience & Rate Limiting Strategy](#resilience--rate-limiting-strategy)
- [Known Limitation: Full-Dataset Materialization Between Read and Write](#known-limitation-full-dataset-materialization-between-read-and-write)

## Multi-Threaded Concurrency vs. OData v4 `$batch`

To scale the execution speed of the sync engine beyond sequential,
record-by-record writes, we analyzed two standard architectural patterns for
accelerating I/O-bound REST workloads: OData v4 `$batch` processing and
client-side multi-threading.

We deliberately chose a **multi-threaded concurrency pool** over `$batch`
operations. This preserves per-record failure isolation and keeps the
transport layer lightweight, at the cost of the connection-overhead
savings `$batch` would otherwise provide.

### The `$batch` Evaluation & The Changeset Trap

OData v4 defines a `$batch` endpoint where multiple operations are packed into a
single `multipart/mixed` HTTP POST request. While this reduces TCP/TLS
connection handshake overhead by roughly three orders of magnitude — one
handshake per 1,000 operations instead of one per operation (matching the
Dataverse batch limit), it introduces notable operational trade-offs:
* **The Atomic Rollback Conflict:** OData batching supports *Changesets*—where
all operations in the group are treated as a single atomic transaction. If a
single payload in a batch of 1,000 fails validation, the entire batch rolls
back. This directly violates our primary acceptance criterion — that one failed
record must never corrupt or roll back successful writes for adjacent,
unrelated records.
* **The Standalone Parsing Overhead:** Bypassing the rollback trap requires
configuring each batch operation as an independent, non-changeset execution
block. However, Python's `requests` library lacks built-in OData batch
parser mechanisms. Implementing this would require writing, testing, and
maintaining a custom parser to build, serialize, and deserialize complex
multipart MIME streams inside the `ODataClient` class, dramatically increasing
the risk of transport-layer regression.
* **API Rate-Limit Parity:** Contrary to common assumptions, Microsoft
Dataverse service protection and daily entitlement quotas count individual
operations *inside* a batch request against your user allocations. While
`$batch` reduces network round-trip latency, it does not bypass the rate-limit
throttling bounds, yet introduces massive client-side overhead to parse and
manage.

### The Winning Solution: Client-Side Multi-Threading

Instead of grouping requests on the server, we implemented a controlled thread
execution pool using a thread-safe connection session manager. This has
three concrete advantages:

* **Granular Isolation & Fault Tolerance:** Each API write is processed on its
own thread — a failed record is caught, logged, and isolated instantly.
The sync engine continues executing the rest of the queue unimpeded.
* **Native Connection Pooling:** By pairing multi-threading with a thread-safe
connection adapter, we reuse TCP handshakes at the transport layer, achieving
nearly identical latency optimization to batching without the structural
complexity of MIME parsing.
* **Dynamic Concurrency Throttling:** Client-side concurrency allows us to
easily listen to Dataverse's `Retry-After` HTTP headers. If we hit service
protection limits, we can dynamically back off or queue-throttle specific
worker threads rather than stalling an entire 1,000-record batch.

## Circuit Breaker vs. Unconditional Retry Exhaustion

`BaseHttpClient`'s retry policy already absorbs transient failures
(429/502/503/504) on a *single* request. It has no opinion on the
*batch* as a whole — a systemic outage (Dataverse down, credentials
revoked mid-run) looks identical to `sync_records()` as a string of
isolated per-record failures, and without a higher-level check, every
remaining record in the batch is still dispatched against an
already-failing destination.

* **Consecutive, not Rate-Based:** `ConsecutiveFailureCircuitBreaker`
  trips after N failures in a row, not a percentage of a sliding
  window. Simpler to reason about, and sufficient for what it needs to
  detect — a sustained, one-sided outage — without the added
  complexity of a windowed rate calculation.
* **Skip, Don't Cancel:** Once tripped, a worker thread checks
  `is_tripped` *before* issuing its request, not after. An
  already-in-flight request (there can be up to `max_workers` of them)
  is not interrupted — cancelling a request mid-flight risks an
  ambiguous outcome (did the PATCH apply or not?) that a clean skip
  avoids entirely.
* **No Resume State, By Design:** A tripped run reports its skipped
  count and exits non-zero; it does not persist which records were
  skipped for a later resume. Every write is an idempotent alternate-
  key upsert (Architectural Directive 2 in `CLAUDE.md`), so re-running
  the whole batch after the outage is fixed reproduces the correct end
  state at no extra cost — a resume mechanism would be complexity
  solving a problem idempotency already solves.
* **Layered at `lag_service_kit`, Not the Runner:** The breaker itself
  knows nothing about HTTP, OData, or Dataverse — it only sees a
  stream of success/failure outcomes. It lives in the cross-service
  scaffolding layer alongside `dedupe_last_seen_chunks`, reusable by
  any future destination's write loop, while the *threshold value* is
  a service-level tuning decision (`defaults.DEFAULT_FAILURE_THRESHOLD`),
  matching how `DEFAULT_CHUNK_SIZE` is handled.

> **Assumption this design depends on:** the "no resume state" argument
> above holds only because every write in this portfolio is an
> idempotent alternate-key `PATCH`. A future destination or protocol
> that *cannot* guarantee idempotent writes (e.g. a plain `POST`-only
> create endpoint, or a bulk-load API without an upsert primitive)
> would need the breaker paired with a real resume/checkpoint
> mechanism — tracking exactly which records were skipped, not just a
> count — before re-running the batch would be safe. That case isn't
> addressed here and isn't in scope for this portfolio at this time; it
> would need to be designed for explicitly if a non-idempotent
> destination is ever added.

## Resilience & Rate Limiting Strategy

- **Current Implementation:** Reactive throttling via HTTP status
  handling (exponential backoff and `Retry-After` header compliance)
  at the transport layer.
- **Sustained Concurrency Strategy:** Under heavy batch loads using
  `ThreadPoolExecutor`, client-side pacing (e.g., Token Bucket) can be
  injected ahead of the transport layer to proactively align
  concurrency with Dataverse Service Protection Limits. Not developed
  in this portfolio — a documented scaling consideration, not a
  built or tested capability. The reactive strategy above is what
  actually ships and runs today.
- **Write-Path Memory Bound:** `BaseODataSyncRunner.sync_records()` holds
  at most `write_window_size` upsert futures in memory at once —
  submitted but not yet collected — rather than materializing one
  future per deduplicated record up front regardless of total feed
  size. Once that many are outstanding, it waits for at least one to
  finish (`concurrent.futures.wait(..., return_when=FIRST_COMPLETED)`),
  collects every future that completed, and submits one new future per
  record still pending, repeating until the whole batch has been
  submitted. This bounds only the write side's in-flight-futures
  memory — it says nothing about the deduplicated dataset itself,
  which is fully materialized in memory before `sync_records()` is
  ever called; see [Known Limitation: Full-Dataset Materialization
  Between Read and Write](#known-limitation-full-dataset-materialization-between-read-and-write)
  below. Records are still submitted to the executor in `records`' own order regardless of
  the window, so the circuit breaker's skip semantics and per-record
  failure isolation are unaffected by windowing; `write_window_size`
  changes only how many futures are ever held in memory at once. See
  `defaults.DEFAULT_WRITE_WINDOW_SIZE` for this service's tuned value
  (5x `DEFAULT_MAX_WORKERS`, keeping every worker fed a queued task
  without holding the whole batch's futures at once) — like
  `max_workers` and `failure_threshold`, `BaseODataSyncRunner.__init__`
  takes no default of its own for it, since a sensible number is a
  service's own operational tuning decision, not this class's. That
  same convention means the `write_window_size >= max_workers`
  relationship above is documented, not enforced: nothing raises if a
  caller sets `write_window_size` lower, and the effect wouldn't be a
  crash, just some workers sitting idle with nothing queued — the
  same trust-the-caller stance this repo already takes with
  `ConsecutiveFailureCircuitBreaker.threshold`, which is equally
  unvalidated.

## Known Limitation: Full-Dataset Materialization Between Read and Write

`load_records()` returns a single, fully deduplicated `pd.DataFrame`
— one row per unique `dedupe_key` value — and `BaseSyncRunner.run()`
holds that whole object in memory for the entire `sync_records()`
call that follows. Neither the read-side chunking
(`ChunkedRecordSource`, `dedupe_last_seen_chunks`) nor the write-side
futures window (`write_window_size`, above) touches this: each bounds
a different thing — raw-row memory during the read pass, and
in-flight-futures memory during the write pass — not the deduplicated
dataset itself, which sits fully materialized between the two.

This is not an oversight; it follows from the dedup semantics chosen.
"Last-write-wins" means a row for a given key seen near the end of the
feed supersedes one seen near the start, so no key's final value can
be known until the entire feed has been read. Nothing short of
changing that guarantee removes the need to see every row before any
row can be finalized.

**The practical ceiling:** memory scales with the feed's *unique key
count*, not its total row count — already an improvement over
concatenating every chunk before deduping (see
`dedupe_last_seen_chunks`'s own docstring) — but a feed with an
extremely large number of unique keys (tens of millions) can still
exhaust available memory before `sync_records()` issues its first
request, regardless of `chunksize` or `write_window_size`. This
portfolio's scope has not required addressing that ceiling; it's
documented here as a known, deliberate boundary, not a bug.

**How this would be removed, if a future feed size required it:**
replace `dedupe_last_seen_chunks`'s in-memory `dict` with a
disk-backed key-value store — a local `sqlite3` table (standard
library, no new dependency) keyed by `dedupe_key`, populated via
`INSERT OR REPLACE` as each chunk streams through. `INSERT OR REPLACE`
gives last-write-wins semantics for free: a later row for the same
key overwrites the earlier one on disk, exactly matching today's dict
behavior, without ever holding more than one chunk's worth of rows in
Python memory at once.

This only works if the SQLite database is backed by an actual file on
disk, not `sqlite3.connect(":memory:")` — an in-memory SQLite database
still consumes RAM exactly like today's `dict` does, defeating the
entire point. The real implementation needs an explicit on-disk temp
file (Python's `tempfile` module), the same "temporary, cleaned up
after use" pattern this repo already applies to Key Vault secrets in
`infra/azure/key-vault/*.sh` — created for the duration of one sync
run and deleted once it finishes, never treated as a durable artifact.
This data has no lifetime beyond a single run: it is never queried by
anything else and never needs concurrent access from another process,
which is exactly why a local, embedded SQLite file is the right tool
here and a networked database (e.g. Postgres) would be unwarranted
complexity — it would trade a zero-dependency, zero-server-process
solution for a running server, a connection/auth story, and a new
external client dependency, none of which this purely single-process,
single-run scratch space needs.

Once the full read pass completes, the deduplicated result lives in
the SQLite file rather than in a `pd.DataFrame`; `sync_records()`
would then read that back out in bounded pages (e.g. a cursor-based
scan, or `SELECT * FROM records LIMIT ? OFFSET ?`) instead of
iterating an in-memory DataFrame, removing the full-materialization
step this section describes. The trade-off: a slower dedup phase
(disk I/O per row instead of a dict lookup) in exchange for a memory
ceiling bounded by disk capacity rather than RAM — the right trade
once RAM is genuinely the binding constraint, and not worth the added
complexity below that size.

---

← [Back to README](../../README.md) · [All docs](../README.md)
