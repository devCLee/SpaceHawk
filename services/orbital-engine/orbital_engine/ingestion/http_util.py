"""Shared HTTP resilience helpers for source connectors.

Two concerns every external connector shares and the dev plan calls out for
Space-Track (Stage 2): **respect API rate limits** and **retry with backoff**.
Both are written with injectable clock/sleep so they can be unit-tested
deterministically without real time or network.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic

import httpx

from orbital_engine.logging import get_logger

log = get_logger("ingestion.http")

# Status codes worth retrying: Space-Track throttling (429) + transient gateway/5xx.
RETRY_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class RateLimiter:
    """Async min-interval limiter (token-bucket of size 1).

    Enforces at most ``max_per_minute`` requests by spacing successive
    ``acquire()`` calls. Space-Track publishes a 30 req/min ceiling; we default
    callers below it. Clock/sleep are injectable for tests.
    """

    def __init__(
        self,
        max_per_minute: int,
        *,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if max_per_minute <= 0:
            raise ValueError("max_per_minute must be positive")
        self.min_interval = 60.0 / max_per_minute
        self._clock = clock
        self._sleep = sleep
        self._last = float("-inf")  # first acquire never waits
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                await self._sleep(wait)
            self._last = self._clock()


async def request_with_retry(
    send: Callable[[], Awaitable[httpx.Response]],
    *,
    max_attempts: int = 4,
    base_delay: float = 0.5,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    retry_status: frozenset[int] = RETRY_STATUS,
) -> httpx.Response:
    """Call ``send`` with exponential backoff on transport errors / retryable status.

    Returns the final response (caller raises for status). Re-raises the last
    transport error if every attempt fails. ``send`` is a thunk so each attempt
    issues a fresh request.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = await send()
        except httpx.TransportError as exc:  # network/timeout — retry
            last_exc = exc
            if attempt == max_attempts:
                raise
            delay = base_delay * 2 ** (attempt - 1)
            log.warning("http.retry.transport", attempt=attempt, delay=delay, error=str(exc))
            await sleep(delay)
            continue
        if resp.status_code in retry_status and attempt < max_attempts:
            delay = base_delay * 2 ** (attempt - 1)
            log.warning("http.retry.status", attempt=attempt, status=resp.status_code, delay=delay)
            await sleep(delay)
            continue
        return resp
    # Unreachable: loop either returns or raises. Satisfy the type checker.
    raise last_exc or RuntimeError("request_with_retry exhausted without a response")
