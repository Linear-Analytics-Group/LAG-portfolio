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

#: Worker threads used to sync records concurrently (see
#: ``runners.odata.BaseODataInventorySyncRunner``). This workload is
#: I/O-bound (waiting on HTTP responses), so threads give real
#: parallelism despite the GIL. If you raise this, the destination
#: client's HTTP connection pool must be sized at least as large or
#: concurrency silently caps at the pool size instead — see
#: ``DataverseInventorySyncRunner.build_client()``, which derives the
#: client's pool size from this same value automatically.
DEFAULT_MAX_WORKERS: int = 10
