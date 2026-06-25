"""DISCOS enrichment: normalization, JSON:API pagination, and the runner pass.

All pure / mock-transport — no live DISCOSweb call. The DB apply
(``repository.apply_enrichments``) is infra-gated and exercised via a fake here.
"""

from __future__ import annotations

import httpx

from orbital_engine.config import Settings
from orbital_engine.ingestion import runner
from orbital_engine.ingestion.discos import (
    DiscosClient,
    DiscosEnrichment,
    normalize,
)
from orbital_engine.ingestion.http_util import RateLimiter


def _item(satno, cospar="2020-001A", **attrs):
    base = {"satno": satno, "cosparId": cospar}
    base.update(attrs)
    return {"id": str(satno), "type": "object", "attributes": base}


def _fast_limiter() -> RateLimiter:
    """A limiter that never actually sleeps (deterministic, no wall-clock wait)."""

    async def _no_sleep(_: float) -> None:
        return None

    return RateLimiter(100_000, sleep=_no_sleep)


# --- normalize (pure) ------------------------------------------------------


def test_normalize_maps_attributes_and_takes_max_dimension() -> None:
    [e] = normalize(
        [
            _item(
                25544,
                objectClass="Payload",
                mass=419600.0,
                shape="Box",
                width=2.0,
                height=4.0,
                depth=3.0,
                xSectMin=1.0,
                xSectAvg=2.5,
                xSectMax=4.0,
            )
        ]
    )
    assert e.norad_cat_id == 25544
    assert e.intl_designator == "2020-001A"
    assert e.object_class == "Payload"
    assert e.mass_kg == 419600.0
    assert e.shape == "Box"
    assert e.span_m == 4.0  # max(width, height, depth)
    assert (e.cross_section_min_m2, e.cross_section_avg_m2, e.cross_section_max_m2) == (1.0, 2.5, 4.0)


def test_normalize_coerces_strings_and_treats_blanks_as_missing() -> None:
    [e] = normalize([_item(1, mass="100.5", diameter="", xSectAvg=None)])
    assert e.mass_kg == 100.5
    assert e.span_m is None
    assert e.cross_section_avg_m2 is None


def test_normalize_skips_rows_without_any_identity() -> None:
    items = [{"id": "x", "type": "object", "attributes": {"satno": None, "cosparId": None, "mass": 5.0}}]
    assert normalize(items) == []


def test_normalize_keeps_cospar_only_rows() -> None:
    [e] = normalize([{"attributes": {"satno": None, "cosparId": "1999-025DEF", "mass": 3.0}}])
    assert e.norad_cat_id is None
    assert e.intl_designator == "1999-025DEF"


# --- client (mock transport) ----------------------------------------------


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="https://discos.test", transport=httpx.MockTransport(handler))


async def test_client_paginates_until_last_page() -> None:
    pages = {
        1: {"data": [_item(1)], "links": {"next": "/api/objects?page[number]=2"},
            "meta": {"pagination": {"currentPage": 1, "totalPages": 2}}},
        2: {"data": [_item(2)], "links": {"next": None},
            "meta": {"pagination": {"currentPage": 2, "totalPages": 2}}},
    }
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        n = int(request.url.params.get("page[number]"))
        seen.append(n)
        return httpx.Response(200, json=pages[n])

    dc = DiscosClient(Settings(discos_api_token="t"), client=_mock_client(handler), limiter=_fast_limiter())
    data = await dc.fetch_objects()
    await dc.aclose()
    assert seen == [1, 2]
    assert [d["attributes"]["satno"] for d in data] == [1, 2]


async def test_client_respects_query_limit() -> None:
    page = {"data": [_item(1), _item(2), _item(3)], "links": {"next": "/api/objects?page[number]=2"},
            "meta": {"pagination": {"currentPage": 1, "totalPages": 5}}}
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=page)

    dc = DiscosClient(
        Settings(discos_api_token="t", discos_query_limit=2),
        client=_mock_client(handler),
        limiter=_fast_limiter(),
    )
    data = await dc.fetch_objects()
    await dc.aclose()
    assert len(data) == 2  # truncated to the cap
    assert calls["n"] == 1  # stopped after the first page


def test_default_client_carries_bearer_token() -> None:
    # The default client (no injected client) authenticates with the token.
    dc = DiscosClient(Settings(discos_api_token="secret"))
    assert dc._client.headers["Authorization"] == "Bearer secret"


# --- runner enrichment pass ------------------------------------------------


async def test_enrich_discos_is_noop_without_token() -> None:
    summary = await runner.enrich_discos(Settings(discos_api_token=None))
    assert summary == {"available": 0, "fetched": 0, "applied": 0}


async def test_enrich_discos_fetches_and_applies(monkeypatch) -> None:
    async def fake_fetch(_settings) -> list[DiscosEnrichment]:
        return [
            DiscosEnrichment(norad_cat_id=1, mass_kg=10.0),
            DiscosEnrichment(intl_designator="2020-001A", shape="Box"),
        ]

    captured: dict = {}

    async def fake_apply(rows) -> int:
        captured["rows"] = rows
        return len(rows)

    monkeypatch.setattr(runner, "fetch_discos", fake_fetch)
    monkeypatch.setattr(runner, "apply_enrichments", fake_apply)

    summary = await runner.enrich_discos(Settings(discos_api_token="t"))
    assert summary == {"available": 1, "fetched": 2, "applied": 2}
    # Enrichment patches reach the repository as plain dicts carrying the join key.
    assert captured["rows"][0]["norad_cat_id"] == 1
    assert captured["rows"][1]["intl_designator"] == "2020-001A"
