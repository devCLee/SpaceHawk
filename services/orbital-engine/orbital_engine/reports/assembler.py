"""Deterministic assembly of the daily report payload from the canonical catalog.

``assemble_daily(report_date, conn)`` runs a fixed set of read-only SQL queries
against the migrated schema (the same tables the ``repository`` module serves)
and folds the rows into a fully-typed :class:`DailyReportPayload`. It is pure
w.r.t. its inputs: no network, no LLM, no randomness, no clock-dependent branches
beyond the explicit future-date guard.

The SQLAlchemy connection is *injected* (the caller owns its lifecycle), mirroring
the engine's read primitive ``get_engine().connect()`` used throughout
``repository``. Tests pass either a live connection (infra-gated round-trip) or a
lightweight fake that satisfies ``await conn.execute(text, params)`` →
``result.mappings()``.

Maneuver analysis reuses the pure detector in ``orbital_engine.maneuver``: for
each surveillance object we count its gp_history epochs; below
``maneuver_min_history_points`` the object is marked ``INSUFFICIENT_HISTORY``
("정보 없음"), otherwise the detector runs over the fetched history.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import text

from orbital_engine.config import Settings, get_settings
from orbital_engine.maneuver import detect_maneuvers
from orbital_engine.reports.schemas import (
    ConjunctionRow,
    CountryBreakdownEntry,
    DailyReportPayload,
    ManeuverDataStatus,
    ManeuverEntry,
    ReentryEntry,
    SurveillanceCategoryCount,
    SurveillanceObjectRow,
    TimeSeriesPoint,
    TimeSeriesSeries,
)

# Cap notable surveillance objects (and their per-object follow-up queries) so a
# full-catalog day stays bounded; the report only tables the most recent payloads.
_SURVEILLANCE_LIMIT = 25

# Minimal engine-side owner-code -> name map. The authoritative COUNTRY_NAMES map
# lives in the web tier (apps/web); the engine has no equivalent, so this covers
# the codes that appear most in the catalog and passes the raw code through for the
# rest (owner_name stays None) rather than inventing a full table. See report notes.
_OWNER_NAMES: dict[str, str] = {
    "US": "미국",
    "PRC": "중국",
    "CIS": "러시아",
    "RU": "러시아",
    "JPN": "일본",
    "ROK": "대한민국",
    "FR": "프랑스",
    "ESA": "유럽우주국",
    "IND": "인도",
    "UK": "영국",
    "DPRK": "북한",
}

# space_object.object_type -> Korean functional category for the §1 집계 표. The
# canonical catalog carries no finer functional tag (recon/통신/기술시험 would need
# upstream enrichment), so the breakdown is by the object_type the schema holds.
_CATEGORY_NAMES: dict[str, str] = {
    "PAYLOAD": "위성(탑재체)",
    "ROCKET BODY": "로켓 본체",
    "DEBRIS": "파편",
    "UNKNOWN": "미상",
    "TBA": "미할당",
}


class _Conn(Protocol):
    """The injected read connection: just what the assembler calls on it."""

    async def execute(self, statement: Any, parameters: Any = ...) -> Any: ...


def _day_window(report_date: date) -> tuple[datetime, datetime]:
    """UTC ``[start, end)`` bracketing the report date's calendar day."""
    start = datetime(report_date.year, report_date.month, report_date.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _owner_name(code: str | None) -> str | None:
    return _OWNER_NAMES.get(code) if code else None


def _regime(apogee_km: float | None, perigee_km: float | None, period_min: float | None) -> str | None:
    """Coarse orbital regime from apsides / period (LEO / MEO / GEO / HEO)."""
    if period_min is not None and 1400.0 <= period_min <= 1480.0:
        return "GEO"
    mean_alt = None
    if apogee_km is not None and perigee_km is not None:
        mean_alt = (apogee_km + perigee_km) / 2.0
        if apogee_km - perigee_km > 5000.0:
            return "HEO"
    if mean_alt is None:
        return None
    if mean_alt < 2000.0:
        return "LEO"
    if mean_alt < 35000.0:
        return "MEO"
    return "GEO"


async def _rows(conn: _Conn, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run one query on the injected connection and return plain dict rows."""
    result = await conn.execute(text(sql), params or {})
    return [dict(row) for row in result.mappings()]


async def _surveillance(conn: _Conn) -> tuple[list[SurveillanceCategoryCount], list[SurveillanceObjectRow]]:
    """§1 — category counts over the live catalog + the notable-object table."""
    counts = await _rows(
        conn,
        "SELECT object_type::text AS object_type, count(*) AS n FROM space_object "
        "WHERE decay_date IS NULL GROUP BY object_type ORDER BY n DESC",
    )
    categories = [
        SurveillanceCategoryCount(
            category=_CATEGORY_NAMES.get(r["object_type"], r["object_type"] or "미상"),
            count=int(r["n"]),
        )
        for r in counts
    ]
    notable = await _rows(
        conn,
        "SELECT object_id, norad_cat_id, object_name, country_code, object_type::text AS object_type, "
        "       apoapsis_km, periapsis_km, period_min "
        "FROM space_object WHERE decay_date IS NULL AND object_type::text = 'PAYLOAD' "
        "ORDER BY epoch DESC LIMIT :lim",
        {"lim": _SURVEILLANCE_LIMIT},
    )
    objects = [
        SurveillanceObjectRow(
            object_id=r["object_id"],
            norad_cat_id=r["norad_cat_id"],
            object_name=r["object_name"],
            owner_code=r["country_code"],
            owner_name=_owner_name(r["country_code"]),
            regime=_regime(r["apoapsis_km"], r["periapsis_km"], r["period_min"]),
            object_type=r["object_type"],
        )
        for r in notable
    ]
    return categories, objects


async def _conjunctions(conn: _Conn, start: datetime, end: datetime) -> list[ConjunctionRow]:
    """§2 — close approaches whose TCA falls inside the report day."""
    rows = await _rows(
        conn,
        "SELECT id, primary_object_id, primary_name, secondary_object_id, secondary_name, "
        "       miss_distance_km, probability, tca, severity::text AS severity "
        "FROM conjunction WHERE tca >= :start AND tca < :end ORDER BY tca ASC",
        {"start": start, "end": end},
    )
    return [
        ConjunctionRow(
            conjunction_id=r["id"],
            primary_object_id=r["primary_object_id"],
            primary_name=r["primary_name"],
            secondary_object_id=r["secondary_object_id"],
            secondary_name=r["secondary_name"],
            miss_distance_km=float(r["miss_distance_km"]),
            probability=float(r["probability"]) if r["probability"] is not None else None,
            tca=r["tca"],
            alert_level=r["severity"],
        )
        for r in rows
    ]


async def _object_history(conn: _Conn, object_id: str, end: datetime) -> list[dict[str, Any]]:
    """gp_history rows for one object up to the end of the report day (oldest-first).

    Only real gp_history columns are selected (name/NORAD live on space_object, not
    the hypertable); the pure detector tolerates their absence (it falls back to the
    object id), and the report does not surface them from the maneuver record.
    """
    return await _rows(
        conn,
        "SELECT object_id, epoch, mean_motion, eccentricity, inclination, ra_of_asc_node, "
        "       semimajor_axis_km, apoapsis_km, periapsis_km "
        "FROM gp_history WHERE object_id = :oid AND epoch < :end ORDER BY epoch ASC",
        {"oid": object_id, "end": end},
    )


def _maneuver_entry(
    row: SurveillanceObjectRow, history: list[dict[str, Any]], settings: Settings
) -> ManeuverEntry:
    """Fold one object's history into a §3 row, marking insufficient history."""
    epochs = len(history)
    if epochs < settings.maneuver_min_history_points:
        return ManeuverEntry(
            object_id=row.object_id,
            norad_cat_id=row.norad_cat_id,
            object_name=row.object_name,
            status=ManeuverDataStatus.INSUFFICIENT_HISTORY,
            history_epochs=epochs,
        )
    maneuvers = detect_maneuvers(history, settings)
    latest = maneuvers[-1] if maneuvers else None
    return ManeuverEntry(
        object_id=row.object_id,
        norad_cat_id=row.norad_cat_id,
        object_name=row.object_name,
        status=ManeuverDataStatus.PRESENT,
        history_epochs=epochs,
        classification=latest.maneuver_type if latest else None,
        delta_v_m_s=latest.delta_v_m_s if latest else None,
        delta_sma_km=latest.delta_sma_km if latest else None,
        epoch=latest.epoch_after if latest else None,
    )


async def _reentries(conn: _Conn, report_date: date) -> list[ReentryEntry]:
    """§4 — objects whose decay_date is the report day (day-resolution window)."""
    rows = await _rows(
        conn,
        "SELECT object_id, norad_cat_id, object_name, country_code "
        "FROM space_object WHERE decay_date = :d ORDER BY object_name",
        {"d": report_date},
    )
    start = datetime(report_date.year, report_date.month, report_date.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    return [
        ReentryEntry(
            object_id=r["object_id"],
            norad_cat_id=r["norad_cat_id"],
            object_name=r["object_name"],
            owner_code=r["country_code"],
            predicted_window_start=start,
            predicted_window_end=end,
        )
        for r in rows
    ]


async def _country_breakdown(conn: _Conn) -> list[CountryBreakdownEntry]:
    """§5 — live-catalog object counts grouped by owner/country code."""
    rows = await _rows(
        conn,
        "SELECT coalesce(country_code, 'UNKNOWN') AS owner_code, count(*) AS n "
        "FROM space_object WHERE decay_date IS NULL GROUP BY owner_code ORDER BY n DESC",
    )
    return [
        CountryBreakdownEntry(
            owner_code=r["owner_code"],
            owner_name=_owner_name(r["owner_code"]),
            count=int(r["n"]),
        )
        for r in rows
    ]


def _time_series(row: SurveillanceObjectRow, history: list[dict[str, Any]]) -> TimeSeriesSeries:
    """Per-object apogee/perigee series for the charts (reuses the fetched history)."""
    points = [
        TimeSeriesPoint(
            epoch=h["epoch"],
            apogee_km=float(h["apoapsis_km"]) if h.get("apoapsis_km") is not None else None,
            perigee_km=float(h["periapsis_km"]) if h.get("periapsis_km") is not None else None,
        )
        for h in history
    ]
    return TimeSeriesSeries(object_id=row.object_id, object_name=row.object_name, points=points)


async def assemble_daily(
    report_date: date,
    conn: _Conn,
    *,
    settings: Settings | None = None,
) -> DailyReportPayload:
    """Assemble the deterministic payload for one day's space-situation report.

    ``conn`` is an injected SQLAlchemy async connection (caller-owned). Raises
    ``ValueError`` for a future ``report_date``; any day with no data returns a
    valid payload with empty sections. An object with fewer than
    ``maneuver_min_history_points`` gp_history epochs is marked "정보 없음" rather
    than crashing the maneuver pass.
    """
    settings = settings or get_settings()
    if report_date > datetime.now(UTC).date():
        raise ValueError(f"report_date {report_date.isoformat()} is in the future")

    start, end = _day_window(report_date)
    categories, objects = await _surveillance(conn)
    conjunctions = await _conjunctions(conn, start, end)
    reentries = await _reentries(conn, report_date)
    country_breakdown = await _country_breakdown(conn)

    maneuvers: list[ManeuverEntry] = []
    time_series: list[TimeSeriesSeries] = []
    for row in objects:
        history = await _object_history(conn, row.object_id, end)
        maneuvers.append(_maneuver_entry(row, history, settings))
        time_series.append(_time_series(row, history))

    return DailyReportPayload(
        report_date=report_date,
        surveillance_categories=categories,
        surveillance_objects=objects,
        conjunctions=conjunctions,
        maneuvers=maneuvers,
        reentries=reentries,
        country_breakdown=country_breakdown,
        time_series=time_series,
    )
