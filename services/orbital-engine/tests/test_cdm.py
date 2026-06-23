"""CDM normalization, severity tiering, and gated fetch (recorded fixtures)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from orbital_engine.config import Settings
from orbital_engine.domain.conjunction import (
    ConjunctionSeverity,
    ConjunctionSource,
    TierThresholds,
    severity_for,
)
from orbital_engine.ingestion import cdm as cdm_mod
from orbital_engine.ingestion.cdm import fetch_cdms, normalize_cdm


def _naive_utc_now() -> datetime:
    """Naive UTC now, matching the watermark format fetch_cdms compares against."""
    return datetime.now(UTC).replace(tzinfo=None)

# A recorded cdm_public record: ISS vs a catalogued debris piece, close & risky.
CDM_HIGH = {
    "CDM_ID": "123456",
    "CREATED": "2026-06-04 00:00:00",
    "TCA": "2026-06-05T12:34:56.000000",
    "MIN_RNG": "0.45",
    "PC": "0.0003",
    "SAT_1_ID": "25544",
    "SAT_1_NAME": "ISS (ZARYA)",
    "SAT_2_ID": "33333",
    "SAT_2_NAME": "COSMOS DEBRIS",
}
CDM_MOD = {
    "CDM_ID": "123457",
    "CREATED": "2026-06-04 03:00:00",
    "TCA": "2026-06-05T18:00:00.000000",
    "MIN_RNG": "3.0",
    "PC": "",  # no Pc reported -> tier falls back to miss distance
    "SAT_1_ID": "40000",
    "SAT_1_NAME": "SAT A",
    "SAT_2_ID": "40001",
    "SAT_2_NAME": "SAT B",
}
CDM_LOW = {
    "CDM_ID": "123458",
    "CREATED": "2026-06-04 06:00:00",
    "TCA": "2026-06-06T00:00:00.000000",
    "MIN_RNG": "25.0",
    "PC": "1e-9",
    "SAT_1_ID": "41000",
    "SAT_1_NAME": "SAT C",
    "SAT_2_ID": "41001",
    "SAT_2_NAME": "SAT D",
}


def test_normalize_cdm_maps_records_to_canonical() -> None:
    conjunctions = normalize_cdm([CDM_HIGH])
    assert len(conjunctions) == 1
    c = conjunctions[0]
    assert c.id == "CDM:123456"
    assert c.source == ConjunctionSource.CDM
    assert c.primary_object_id == "SH:CAT:000025544"
    assert c.secondary_object_id == "SH:CAT:000033333"
    assert c.primary_name == "ISS (ZARYA)"
    assert c.miss_distance_km == 0.45
    assert c.probability == 0.0003
    assert c.severity == ConjunctionSeverity.HIGH


def test_normalize_cdm_tiers_track_pc_and_miss() -> None:
    by_id = {c.id: c for c in normalize_cdm([CDM_HIGH, CDM_MOD, CDM_LOW])}
    assert by_id["CDM:123456"].severity == ConjunctionSeverity.HIGH
    assert by_id["CDM:123457"].severity == ConjunctionSeverity.MOD
    assert by_id["CDM:123457"].probability is None  # blank PC -> None
    assert by_id["CDM:123458"].severity == ConjunctionSeverity.LOW


def test_normalize_cdm_skips_rows_without_tca_or_range() -> None:
    bad_no_rng = {**CDM_HIGH, "CDM_ID": "x", "MIN_RNG": ""}
    bad_no_tca = {**CDM_HIGH, "CDM_ID": "y", "TCA": ""}
    assert normalize_cdm([bad_no_rng, bad_no_tca, CDM_HIGH]) == normalize_cdm([CDM_HIGH])


def test_normalize_cdm_respects_limit() -> None:
    assert len(normalize_cdm([CDM_HIGH, CDM_MOD, CDM_LOW], limit=2)) == 2


def test_severity_for_thresholds_are_tunable() -> None:
    strict = TierThresholds(pc_high=1.0, pc_mod=1.0, miss_high_km=0.1, miss_mod_km=0.5)
    # With strict Pc/HIGH gates the same 0.45 km / 3e-4 Pc approach drops to MOD
    # (default thresholds would call it HIGH) — tiering is genuinely config-driven.
    assert severity_for(0.0003, 0.45) == ConjunctionSeverity.HIGH
    assert severity_for(0.0003, 0.45, strict) == ConjunctionSeverity.MOD


async def test_fetch_cdms_returns_empty_without_credentials() -> None:
    assert await fetch_cdms(Settings()) == []


class _FakeClient:
    """Stand-in for SpaceTrackClient: records the `since` it was queried with."""

    def __init__(self, records: list[dict]) -> None:
        self.records = records
        self.queried_since = None
        self.closed = False

    async def query_cdm(self, since=None, *, limit=None):
        self.queried_since = since
        return self.records

    async def aclose(self) -> None:
        self.closed = True


async def test_fetch_cdms_normalizes_and_advances_watermark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker: dict[str, str] = {}

    async def fake_read(scope: str):
        return marker.get(scope)

    async def fake_write(scope: str, ts: str):
        marker[scope] = ts

    monkeypatch.setattr(cdm_mod, "read_sync_marker", fake_read)
    monkeypatch.setattr(cdm_mod, "write_sync_marker", fake_write)

    fake = _FakeClient([CDM_HIGH, CDM_LOW])
    # fetch_cdms imports SpaceTrackClient from the spacetrack module at call time.
    from orbital_engine.ingestion import spacetrack

    monkeypatch.setattr(spacetrack, "SpaceTrackClient", lambda settings: fake)

    conjunctions = await fetch_cdms(
        Settings(spacetrack_identity="u", spacetrack_password="p", cdm_lookback_days=2.0)
    )

    assert {c.id for c in conjunctions} == {"CDM:123456", "CDM:123458"}
    assert fake.closed is True
    # First run has no watermark, so `since` is clamped to the recent horizon
    # (now - cdm_lookback_days) rather than None — we never fetch the whole feed.
    horizon = _naive_utc_now() - timedelta(days=2.0)
    assert fake.queried_since is not None
    assert abs((fake.queried_since - horizon).total_seconds()) < 60
    assert marker[cdm_mod.CDM_MARKER_SCOPE] == "2026-06-04 06:00:00"


async def test_fetch_cdms_clamps_stale_watermark_to_recent_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ancient watermark must not trap ingestion in weeks-old CDMs.

    Regression for "근접 분석 shows May only": the watermark was stuck weeks back,
    so each fetch re-pulled stale (past-TCA) messages. fetch_cdms now clamps the
    lower bound up to ~now - cdm_lookback_days, self-healing in a single fetch.
    """
    marker = {cdm_mod.CDM_MARKER_SCOPE: "2026-01-01 00:00:00"}  # ancient watermark

    async def fake_read(scope: str):
        return marker.get(scope)

    async def fake_write(scope: str, ts: str):
        marker[scope] = ts

    monkeypatch.setattr(cdm_mod, "read_sync_marker", fake_read)
    monkeypatch.setattr(cdm_mod, "write_sync_marker", fake_write)

    fake = _FakeClient([CDM_HIGH])
    from orbital_engine.ingestion import spacetrack

    monkeypatch.setattr(spacetrack, "SpaceTrackClient", lambda settings: fake)

    await fetch_cdms(
        Settings(spacetrack_identity="u", spacetrack_password="p", cdm_lookback_days=2.0)
    )

    horizon = _naive_utc_now() - timedelta(days=2.0)
    assert fake.queried_since is not None
    assert abs((fake.queried_since - horizon).total_seconds()) < 60  # not 2026-01-01


async def test_fetch_cdms_keeps_fresh_watermark(monkeypatch: pytest.MonkeyPatch) -> None:
    """A recent watermark wins over the horizon, so a healthy feed stays incremental."""
    recent = _naive_utc_now() - timedelta(hours=1)
    marker = {cdm_mod.CDM_MARKER_SCOPE: recent.strftime("%Y-%m-%d %H:%M:%S")}

    async def fake_read(scope: str):
        return marker.get(scope)

    async def fake_write(scope: str, ts: str):
        marker[scope] = ts

    monkeypatch.setattr(cdm_mod, "read_sync_marker", fake_read)
    monkeypatch.setattr(cdm_mod, "write_sync_marker", fake_write)

    fake = _FakeClient([CDM_HIGH])
    from orbital_engine.ingestion import spacetrack

    monkeypatch.setattr(spacetrack, "SpaceTrackClient", lambda settings: fake)

    await fetch_cdms(
        Settings(spacetrack_identity="u", spacetrack_password="p", cdm_lookback_days=2.0)
    )

    assert fake.queried_since is not None
    assert abs((fake.queried_since - recent).total_seconds()) < 2  # watermark, not horizon
