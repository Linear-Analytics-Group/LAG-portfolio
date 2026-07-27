"""Thread-safe circuit breaker for batch write loops, any destination."""

import threading


class ConsecutiveFailureCircuitBreaker:
    """Trips after a run of consecutive failures, latching open.

    Destination- and protocol-agnostic: it only ever sees a stream of
    success/failure outcomes, never a client, a record, or an HTTP
    status code, so it is reusable by any future write loop regardless
    of wire protocol (see
    ``lag_service_kit.runners.odata.BaseODataSyncRunner`` for the one
    that uses it today).

    Notes
    -----
    "Consecutive" is tracked in completion order, not submission order.
    Under concurrent execution (see
    ``BaseODataSyncRunner.sync_records``), several calls are
    in flight at once, so there is no single well-defined "order" to
    count against — completion order is the only one this class can
    observe. A lone success interleaved among a run of failures resets
    the counter, same as it would in a strictly sequential loop; this
    is a deliberate simplification (a true failure-rate breaker would
    use a sliding window instead), acceptable because the counter only
    needs to detect a sustained, one-sided outage, not classify every
    possible failure pattern.

    Once tripped, stays tripped for the lifetime of this instance —
    there is no auto-recovery mid-run. A caller constructs a fresh
    instance per run (see ``sync_records``'s local ``breaker``
    variable), so a later, separate run always starts closed. Every
    write in this codebase is an idempotent alternate-key upsert (see
    CLAUDE.md Architectural Directive 2), so there is no need to
    resume a tripped run's skipped records specifically — re-running
    the whole batch after the underlying issue is fixed reproduces the
    same result at no extra cost.
    """

    def __init__(self, threshold: int) -> None:
        """Set the consecutive-failure count that trips this breaker.

        Parameters
        ----------
        threshold : int
            Number of consecutive failures required to trip open. No
            default here: a sensible number is a property of the
            calling service's own operational tolerance (see e.g.
            ``defaults.DEFAULT_FAILURE_THRESHOLD`` in
            ``services/inventory-sync-engine``), not of this class —
            mirroring ``CsvRecordReader.load_chunks``,
            ``dedupe_last_seen_chunks``, and
            ``BaseODataSyncRunner.__init__``'s own
            ``max_workers``/``failure_threshold`` parameters, none of
            which bake in a default for a value that's genuinely a
            service's own operational tuning decision.

        Returns
        -------
        None
        """
        self._threshold = threshold
        self._consecutive_failures = 0
        self._tripped = False
        self._lock = threading.Lock()

    @property
    def is_tripped(self) -> bool:
        """Whether this breaker has latched open.

        Returns
        -------
        bool
            ``True`` once :attr:`threshold` consecutive failures have
            been recorded, and permanently thereafter.
        """
        with self._lock:
            return self._tripped

    def record_success(self) -> None:
        """Record a successful call, resetting the consecutive count.

        Returns
        -------
        None

        Notes
        -----
        Has no effect on an already-tripped breaker — once latched,
        a success can never untrip it (see the class docstring).
        """
        with self._lock:
            if not self._tripped:
                self._consecutive_failures = 0

    def record_failure(self) -> bool:
        """Record a failed call, tripping the breaker at the threshold.

        Returns
        -------
        bool
            ``True`` only on the single call whose failure count first
            reaches :attr:`threshold` — i.e., the call that *just*
            tripped the breaker. ``False`` on every other call,
            including calls after it is already tripped, so a caller
            can log the trip exactly once rather than once per
            subsequent failure.
        """
        with self._lock:
            if self._tripped:
                return False
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._threshold:
                self._tripped = True
                return True
            return False
