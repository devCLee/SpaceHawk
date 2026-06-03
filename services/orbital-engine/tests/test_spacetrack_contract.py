"""Space-Track connector contract test against a recorded HTTP transport.

Uses httpx.MockTransport so the auth->query flow, response parsing, and
incremental predicate are exercised end-to-end without touching the network.
"""

from __future__ import annotations

import httpx

from orbital_engine.config import Settings
from orbital_engine.ingestion.http_util import RateLimiter
from orbital_engine.ingestion.spacetrack import LOGIN_PATH, SpaceTrackClient

GP_RECORD = {
    "OBJECT_NAME": "ISS (ZARYA)",
    "OBJECT_ID": "1998-067A",
    "NORAD_CAT_ID": "25544",
    "OBJECT_TYPE": "PAYLOAD",
    "EPOCH": "2024-03-10T12:25:39.999999",
    "CREATION_DATE": "2024-03-10 18:00:00",
    "MEAN_MOTION": "15.50079139",
    "ECCENTRICITY": "0.0006008",
    "INCLINATION": "51.6439",
    "RA_OF_ASC_NODE": "32.1281",
    "ARG_OF_PERICENTER": "76.8618",
    "MEAN_ANOMALY": "58.0505",
    "TLE_LINE0": "0 ISS (ZARYA)",
    "TLE_LINE1": "1 25544U 98067A   24070.51782407  .00006484  00000-0  12035-3 0  9993",
    "TLE_LINE2": "2 25544  51.6439  32.1281 0006008  76.8618  58.0505 15.50079139442263",
}


def _make_client(record_paths: list[str]) -> SpaceTrackClient:
    def handler(request: httpx.Request) -> httpx.Response:
        record_paths.append(request.url.path)
        if request.url.path == LOGIN_PATH:
            return httpx.Response(200, text="")
        if "/class/gp" in request.url.path:
            return httpx.Response(200, json=[GP_RECORD])
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    settings = Settings(
        spacetrack_base_url="https://space-track.test",
        spacetrack_identity="u",
        spacetrack_password="p",
    )
    http = httpx.AsyncClient(base_url=settings.spacetrack_base_url, transport=transport)
    # Fast limiter so the contract test doesn't actually wait between requests.
    return SpaceTrackClient(settings, client=http, limiter=RateLimiter(100000))


async def test_login_then_query_parses_records() -> None:
    paths: list[str] = []
    client = _make_client(paths)
    try:
        records = await client.query_gp()
    finally:
        await client.aclose()
    assert len(records) == 1
    assert records[0]["NORAD_CAT_ID"] == "25544"
    # Auth happened first, exactly once, before the gp query.
    assert paths[0] == LOGIN_PATH
    assert paths.count(LOGIN_PATH) == 1
    assert any("/class/gp" in p for p in paths)


async def test_incremental_predicate_reaches_the_wire() -> None:
    from datetime import datetime

    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        if request.url.path == LOGIN_PATH:
            return httpx.Response(200, text="")
        return httpx.Response(200, json=[])

    settings = Settings(
        spacetrack_base_url="https://space-track.test",
        spacetrack_identity="u",
        spacetrack_password="p",
    )
    http = httpx.AsyncClient(base_url=settings.spacetrack_base_url, transport=httpx.MockTransport(handler))
    client = SpaceTrackClient(settings, client=http, limiter=RateLimiter(100000))
    try:
        await client.query_gp(datetime(2024, 3, 10, 18, 0, 0))
    finally:
        await client.aclose()
    gp_urls = [u for u in captured if "class/gp" in u]
    assert gp_urls and "CREATION_DATE" in gp_urls[0]
