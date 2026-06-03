"""RateLimiter spacing + request_with_retry backoff (deterministic, no network)."""

from __future__ import annotations

import httpx
import pytest

from orbital_engine.ingestion.http_util import RateLimiter, request_with_retry


def _fake_clock(values: list[float]):
    """Clock that yields successive values, holding the last one."""
    state = {"i": 0}

    def clock() -> float:
        i = min(state["i"], len(values) - 1)
        state["i"] += 1
        return values[i]

    return clock


async def test_rate_limiter_first_acquire_does_not_wait() -> None:
    slept: list[float] = []

    async def sleep(d: float) -> None:
        slept.append(d)

    limiter = RateLimiter(60, clock=lambda: 0.0, sleep=sleep)
    await limiter.acquire()
    assert slept == []


async def test_rate_limiter_spaces_successive_calls() -> None:
    slept: list[float] = []

    async def sleep(d: float) -> None:
        slept.append(d)

    # 60/min -> 1.0s min interval; clock pinned at 0 so the 2nd call must wait ~1s.
    limiter = RateLimiter(60, clock=lambda: 0.0, sleep=sleep)
    await limiter.acquire()
    await limiter.acquire()
    assert slept == [pytest.approx(1.0)]


def test_rate_limiter_rejects_nonpositive_rate() -> None:
    with pytest.raises(ValueError):
        RateLimiter(0)


async def test_retry_succeeds_after_retryable_status() -> None:
    slept: list[float] = []
    responses = [httpx.Response(503), httpx.Response(500), httpx.Response(200)]
    calls = {"n": 0}

    async def send() -> httpx.Response:
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    async def sleep(d: float) -> None:
        slept.append(d)

    resp = await request_with_retry(send, base_delay=0.5, sleep=sleep)
    assert resp.status_code == 200
    assert calls["n"] == 3
    assert slept == [pytest.approx(0.5), pytest.approx(1.0)]  # exponential backoff


async def test_retry_recovers_from_transport_error() -> None:
    calls = {"n": 0}

    async def send() -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200)

    async def sleep(d: float) -> None:
        return None

    resp = await request_with_retry(send, sleep=sleep)
    assert resp.status_code == 200
    assert calls["n"] == 2


async def test_retry_reraises_after_exhausting_transport_errors() -> None:
    async def send() -> httpx.Response:
        raise httpx.ConnectError("boom")

    async def sleep(d: float) -> None:
        return None

    with pytest.raises(httpx.ConnectError):
        await request_with_retry(send, max_attempts=3, sleep=sleep)


async def test_retry_returns_immediately_on_non_retryable_status() -> None:
    calls = {"n": 0}

    async def send() -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    async def sleep(d: float) -> None:
        raise AssertionError("should not sleep on a non-retryable status")

    resp = await request_with_retry(send, sleep=sleep)
    assert resp.status_code == 404
    assert calls["n"] == 1
