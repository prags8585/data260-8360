"""HW5 Part 3: per-attempt timeouts + bounded exponential backoff.

call_with_retry(fn, policy) runs fn up to policy.max_attempts times.
  - each attempt gets policy.timeout_s (enforced with a worker thread)
  - only TransientError / TimeoutError are retried; anything else
    (validation problems, programming errors) propagates immediately
  - the wait before retry n is base_delay_s * backoff_factor**(n-1),
    capped at max_delay_s, so the total waiting time is bounded
  - when every attempt fails, RetriesExhausted is raised so the caller can
    turn it into a clean {ok: false, ...} result instead of crashing
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("resilience")
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="attempt")


class TransientError(Exception):
    """A failure that is worth retrying (connection reset, injected fault, ...)."""


class RetriesExhausted(Exception):
    def __init__(self, attempts: int, errors: list[str]):
        super().__init__(f"failed after {attempts} attempt(s): {errors[-1]}")
        self.attempts = attempts
        self.errors = errors


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    timeout_s: float = 1.0
    base_delay_s: float = 0.05
    backoff_factor: float = 2.0
    max_delay_s: float = 0.5

    def delay_before_retry(self, retry_number: int) -> float:
        return min(self.base_delay_s * self.backoff_factor ** (retry_number - 1), self.max_delay_s)

    def worst_case_seconds(self) -> float:
        waits = sum(self.delay_before_retry(n) for n in range(1, self.max_attempts))
        return self.max_attempts * self.timeout_s + waits


INTERACTIVE = RetryPolicy(max_attempts=3, timeout_s=1.0, base_delay_s=0.05, backoff_factor=2.0, max_delay_s=0.5)
BATCH = RetryPolicy(max_attempts=6, timeout_s=10.0, base_delay_s=0.5, backoff_factor=2.0, max_delay_s=8.0)


@dataclass
class AttemptLog:
    attempts: int = 0
    events: list[dict] = field(default_factory=list)


def _run_with_timeout(fn: Callable[[], Any], timeout_s: float) -> Any:
    future = _pool.submit(fn)
    try:
        return future.result(timeout=timeout_s)
    except FutureTimeout:
        future.cancel()
        raise TimeoutError(f"attempt timed out after {timeout_s:.2f}s")


def call_with_retry(fn: Callable[[], Any], policy: RetryPolicy = INTERACTIVE, *,
                    sleep: Callable[[float], None] = time.sleep, trace: AttemptLog | None = None) -> Any:
    errors: list[str] = []
    for attempt in range(1, policy.max_attempts + 1):
        try:
            result = _run_with_timeout(fn, policy.timeout_s)
            if trace is not None:
                trace.attempts = attempt
                trace.events.append({"attempt": attempt, "outcome": "success"})
            log.info("attempt %d/%d succeeded", attempt, policy.max_attempts)
            return result
        except (TransientError, TimeoutError) as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            if trace is not None:
                trace.attempts = attempt
                trace.events.append({"attempt": attempt, "outcome": "failure", "error": errors[-1]})
            if attempt == policy.max_attempts:
                log.warning("attempt %d/%d failed, giving up: %s", attempt, policy.max_attempts, errors[-1])
                raise RetriesExhausted(attempt, errors) from exc
            delay = policy.delay_before_retry(attempt)
            log.warning("attempt %d/%d failed (%s); retrying in %.3fs", attempt, policy.max_attempts, errors[-1], delay)
            sleep(delay)
    raise AssertionError("unreachable")
