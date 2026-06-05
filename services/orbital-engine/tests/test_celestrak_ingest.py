"""Celestrak normalization (pure, no network)."""

from __future__ import annotations

import httpx
import pytest

from orbital_engine.config import Settings
from orbital_engine.domain.space_object import DataSource
from orbital_engine.ingestion import celestrak
from orbital_engine.ingestion.celestrak import _parse_tle_text, normalize

ISS_L1 = "1 25544U 98067A   24070.51782407  .00006484  00000-0  12035-3 0  9993"
ISS_L2 = "2 25544  51.6439  32.1281 0006008  76.8618  58.0505 15.50079139442263"
ISS_TLE = f"ISS (ZARYA)\n{ISS_L1}\n{ISS_L2}\n"

ISS_OMM = {
    "OBJECT_NAME": "ISS (ZARYA)",
    "OBJECT_ID": "1998-067A",
    "NORAD_CAT_ID": 25544,
    "EPOCH": "2024-03-10T12:25:39.999",
    "MEAN_MOTION": 15.50079139,
    "ECCENTRICITY": 0.0006008,
    "INCLINATION": 51.6439,
    "RA_OF_ASC_NODE": 32.1281,
    "ARG_OF_PERICENTER": 76.8618,
    "MEAN_ANOMALY": 58.0505,
    "CLASSIFICATION_TYPE": "U",
}


def test_parse_tle_text_keys_by_norad() -> None:
    parsed = _parse_tle_text(ISS_TLE)
    assert 25544 in parsed
    assert parsed[25544][1] == ISS_L1


def test_normalize_merges_tle_and_derives_usoid() -> None:
    objects = normalize([ISS_OMM], ISS_TLE)
    assert len(objects) == 1
    obj = objects[0]
    assert obj.object_id == "SH:CAT:000025544"
    assert obj.data_source == DataSource.CELESTRAK
    assert obj.tle_line1 == ISS_L1
    assert obj.tle_line2 == ISS_L2


def test_normalize_skips_records_without_tle() -> None:
    # OMM record whose NORAD id has no matching TLE line is dropped (can't propagate).
    objects = normalize([{**ISS_OMM, "NORAD_CAT_ID": 99999}], ISS_TLE)
    assert objects == []


def test_normalize_respects_limit() -> None:
    two = [ISS_OMM, {**ISS_OMM, "NORAD_CAT_ID": 25544, "OBJECT_NAME": "DUP"}]
    assert len(normalize(two, ISS_TLE, limit=1)) == 1


# --- Throttle handling (regression: Celestrak per-group 403 must not 500) ------

_THROTTLE_BODY = (
    "GP data has not updated since your last successful\r\n"
    "download of GROUP=active at 2026-06-05 08:05:02 UTC."
)


class _FakeResp:
    def __init__(self, status_code: int, *, text: str = "", json_data=None) -> None:
        self.status_code = status_code
        self.text = text
        self._json = json_data

    def json(self):
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=None, response=None  # type: ignore[arg-type]
            )


class _FakeClient:
    """Minimal stand-in for httpx.AsyncClient that replays queued responses."""

    def __init__(self, responses: list[_FakeResp]) -> None:
        self._responses = list(responses)

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False

    async def get(self, _url, params=None) -> _FakeResp:
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_fetch_celestrak_returns_empty_when_throttled(monkeypatch) -> None:
    # Both same-group requests come back 403 "not updated" — fetch must yield []
    # (no new data), never raise (which the endpoint would surface as a 500).
    responses = [_FakeResp(403, text=_THROTTLE_BODY), _FakeResp(403, text=_THROTTLE_BODY)]
    monkeypatch.setattr(celestrak.httpx, "AsyncClient", lambda *a, **k: _FakeClient(responses))
    assert await celestrak.fetch_celestrak(Settings()) == []


@pytest.mark.asyncio
async def test_fetch_celestrak_throttle_on_second_request(monkeypatch) -> None:
    # The real-world case: the first (JSON) request succeeds and sets Celestrak's
    # per-group marker, so the second (TLE) request is throttled. Still non-fatal.
    responses = [_FakeResp(200, json_data=[ISS_OMM]), _FakeResp(403, text=_THROTTLE_BODY)]
    monkeypatch.setattr(celestrak.httpx, "AsyncClient", lambda *a, **k: _FakeClient(responses))
    assert await celestrak.fetch_celestrak(Settings()) == []
