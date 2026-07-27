"""Unit tests for lag_service_kit.circuit_breaker."""

import threading

import pytest
from lag_service_kit.circuit_breaker import ConsecutiveFailureCircuitBreaker

pytestmark = pytest.mark.unit


def test_starts_closed() -> None:
    """A freshly constructed breaker has not tripped."""
    breaker = ConsecutiveFailureCircuitBreaker(threshold=3)
    assert breaker.is_tripped is False


def test_trips_after_reaching_the_threshold() -> None:
    """The breaker trips on the failure that reaches the threshold."""
    breaker = ConsecutiveFailureCircuitBreaker(threshold=3)

    assert breaker.record_failure() is False
    assert breaker.is_tripped is False
    assert breaker.record_failure() is False
    assert breaker.is_tripped is False
    assert breaker.record_failure() is True
    assert breaker.is_tripped is True


def test_a_success_before_the_threshold_resets_the_count() -> None:
    """A success interleaved among failures resets the streak."""
    breaker = ConsecutiveFailureCircuitBreaker(threshold=3)

    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    breaker.record_failure()

    assert breaker.is_tripped is False


def test_stays_tripped_even_after_a_later_success() -> None:
    """Once latched, a success can never untrip the breaker."""
    breaker = ConsecutiveFailureCircuitBreaker(threshold=2)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_tripped is True

    breaker.record_success()

    assert breaker.is_tripped is True


def test_record_failure_returns_false_after_already_tripped() -> None:
    """Only the call that trips the breaker returns True, never again.

    Reproduces an already-in-flight request completing after the trip:
    with concurrent workers, a request that started before the breaker
    tripped still runs to completion and still reports its own outcome,
    so record_failure() must absorb a post-trip failure without
    re-tripping (returning True again) or over-counting.
    """
    breaker = ConsecutiveFailureCircuitBreaker(threshold=2)

    assert breaker.record_failure() is False
    assert breaker.record_failure() is True
    assert breaker.record_failure() is False
    assert breaker.record_failure() is False


def test_threshold_of_one_trips_on_the_first_failure() -> None:
    """A threshold of 1 trips immediately, with no tolerance."""
    breaker = ConsecutiveFailureCircuitBreaker(threshold=1)
    assert breaker.record_failure() is True


def test_concurrent_failures_trip_exactly_once() -> None:
    """N threads racing past the threshold trip the breaker exactly once.

    A ``threading.Barrier`` forces every thread to call
    ``record_failure`` at the same instant, exercising the real
    concurrent path this breaker is actually used under (see
    ``BaseODataSyncRunner.sync_records``) rather than only
    ever calling it from one thread at a time.

    This does not, by itself, prove the internal lock is load-bearing:
    unlike a slow I/O call, incrementing a plain integer is fast enough
    that CPython's GIL leaves no real window for two threads to
    interleave the read and the write, lock or no lock — confirmed by
    running this same scenario 300 times with the lock temporarily
    removed, without once observing more than one thread report
    tripping it. The lock stays in the implementation regardless: it
    is a public class, and "the GIL happens to make this atomic today"
    is not a portability guarantee across Python implementations (a
    no-GIL CPython build, for one) or safe against a future change
    that adds slower work inside the critical section.
    """
    thread_count = 20
    breaker = ConsecutiveFailureCircuitBreaker(threshold=thread_count)
    barrier = threading.Barrier(thread_count)
    trip_results: list[bool] = [False] * thread_count

    def worker(index: int) -> None:
        barrier.wait()
        trip_results[index] = breaker.record_failure()

    threads = [
        threading.Thread(target=worker, args=(i,))
        for i in range(thread_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert breaker.is_tripped is True
    assert sum(trip_results) == 1
