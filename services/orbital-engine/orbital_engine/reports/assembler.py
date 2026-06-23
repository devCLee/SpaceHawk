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

Satellite passes (§2/§3) reuse the pure geometry compute in
``orbital_engine.reports.passes`` (R2): for each report-country object with a
usable TLE the assembler calls ``predict_passes(...)`` over the report day from
the 대전 KARI ground station and maps each :class:`~orbital_engine.reports.passes.PassGeometry`
onto a :class:`SatellitePass`. Debris risk (§5) reuses
``orbital_engine.debris_risk`` (``risk_score`` / ``risk_level``).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import text

from orbital_engine.config import Settings
from orbital_engine.debris_risk import circular_speed_km_s, risk_level, risk_score
from orbital_engine.reports.passes import KARI, predict_passes
from orbital_engine.reports.schemas import (
    ConjunctionRow,
    CountryActivity,
    DailyReportPayload,
    DebrisRiskCounts,
    HighRiskDebrisRow,
    ReportCountry,
    SatellitePass,
    WatchlistRow,
)

# --- Cost controls (full-catalog days must stay bounded) ---------------------
# §2/§3 pass computation is the only O(n) propagation in the assembler. We bound
# it twice: (a) only consider the most-recently-tracked objects per country, and
# (b) stop once enough passes have been collected. predict_passes itself samples
# the day at _PASS_STEP_S so a single object is ~2880 SGP4 calls; capping objects
# keeps the worst case predictable. Empty when no object yields a pass.
_PASS_CANDIDATES_PER_COUNTRY = 40
_PASS_MAX_PASSES_PER_COUNTRY = 25
_PASS_STEP_S = 30.0
# Elevation mask for "한반도 통과": 10 deg is a sensible operational horizon
# (clears terrain/atmosphere clutter) while still catching meaningful overpasses.
_PASS_MIN_ELEVATION_DEG = 10.0

# Cap the §5c high-risk debris table so a debris-heavy day stays tabular.
_HIGH_RISK_DEBRIS_LIMIT = 25

# Map each ReportCountry (NK/CN/RU/JP) -> the Space-Track owner code(s) that
# appear in the catalog's ``country_code`` column. Codes taken verbatim from
# apps/web/src/app/data/countries.ts (COUNTRY_NAMES / COUNTRY_ISO):
#   China=PRC, Russia=CIS, Japan=JPN, North Korea=PRK. We keep RU as a Russia
#   alias too (the engine's _OWNER_NAMES historically carried both CIS and RU).
_REPORT_COUNTRY_OWNER_CODES: dict[ReportCountry, tuple[str, ...]] = {
    ReportCountry.NORTH_KOREA: ("PRK",),
    ReportCountry.CHINA: ("PRC",),
    ReportCountry.RUSSIA: ("CIS", "RU"),
    ReportCountry.JAPAN: ("JPN",),
}

_REPORT_COUNTRY_NAMES: dict[ReportCountry, str] = {
    ReportCountry.NORTH_KOREA: "북한",
    ReportCountry.CHINA: "중국",
    ReportCountry.RUSSIA: "러시아",
    ReportCountry.JAPAN: "일본",
}

# Minimal engine-side owner-code -> Korean name map (mirrors countries.ts subset).
# Unmapped codes pass through as None (no invented names). See report notes.
_OWNER_NAMES: dict[str, str] = {
    "US": "미국",
    "PRC": "중국",
    "CIS": "러시아",
    "RU": "러시아",
    "JPN": "일본",
    "PRK": "북한",
    "ROK": "대한민국",
    "FR": "프랑스",
    "ESA": "유럽우주국",
    "IND": "인도",
    "UK": "영국",
}

# Risk-level (debris_risk.risk_level) -> DebrisRiskCounts field / §5c 위험등급.
_RISK_KO: dict[str, str] = {
    "Critical": "심각",
    "High": "높음",
    "Medium": "보통",
    "Low": "낮음",
}
# Levels surfaced in the §5c high-risk table (Critical/High), highest first.
_HIGH_RISK_LEVELS: tuple[str, ...] = ("Critical", "High")


class _Conn(Protocol):
    """The injected read connection: just what the assembler calls on it."""

    async def execute(self, statement: Any, parameters: Any = ...) -> Any: ...


def _day_window(report_date: date) -> tuple[datetime, datetime]:
    """UTC ``[start, end)`` bracketing the report date's calendar day."""
    start = datetime(report_date.year, report_date.month, report_date.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _owner_name(code: str | None) -> str | None:
    return _OWNER_NAMES.get(code) if code else None


def _regime(
    apoapsis_km: float | None,
    periapsis_km: float | None,
    period_min: float | None,
    eccentricity: float | None,
) -> str | None:
    """Coarse orbital regime (LEO / MEO / GEO / HEO), or None when undeterminable.

    Mirrors the web classifier in ``apps/web/src/app/utils/sgp4FromTle.ts``
    (HEO when highly eccentric) combined with the apside thresholds in the R3
    spec:
      * HEO — eccentricity > 0.25 (highly elliptical), regardless of altitude;
      * GEO — mean altitude within ~35786 ± 1500 km (geosynchronous shell);
      * LEO — mean altitude < 2000 km;
      * MEO — 2000 km <= mean altitude < GEO band.
    Mean altitude = (apoapsis + periapsis) / 2. Returns None when neither the
    apsides nor the period give an altitude.
    """
    if eccentricity is not None and eccentricity > 0.25:
        return "HEO"
    mean_alt: float | None = None
    if apoapsis_km is not None and periapsis_km is not None:
        mean_alt = (apoapsis_km + periapsis_km) / 2.0
    elif period_min is not None and 1410.0 <= period_min <= 1450.0:
        return "GEO"
    if mean_alt is None:
        return None
    if 34286.0 <= mean_alt <= 37286.0:
        return "GEO"
    if mean_alt < 2000.0:
        return "LEO"
    if mean_alt < 34286.0:
        return "MEO"
    return "GEO"


def _mean_altitude_km(apoapsis_km: float | None, periapsis_km: float | None) -> float | None:
    """Mean shell altitude [km] = (apoapsis + periapsis) / 2, or None."""
    if apoapsis_km is None or periapsis_km is None:
        return None
    return (apoapsis_km + periapsis_km) / 2.0


async def _rows(conn: _Conn, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run one query on the injected connection and return plain dict rows."""
    result = await conn.execute(text(sql), params or {})
    return [dict(row) for row in result.mappings()]


async def _watchlist(conn: _Conn) -> tuple[list[WatchlistRow], WatchlistRow]:
    """§1 — ALL catalog objects grouped by owner country × regime, plus totals.

    Counts are derived in Python (regime needs the eccentricity/apside logic the
    SQL has no clean expression for). One pass over the live catalog; objects
    with an undeterminable regime are tallied into the row total but not into any
    regime column.
    """
    rows = await _rows(
        conn,
        "SELECT coalesce(country_code, 'UNKNOWN') AS owner_code, "
        "       apoapsis_km, periapsis_km, period_min, eccentricity "
        "FROM space_object WHERE decay_date IS NULL",
    )

    buckets: dict[str, dict[str, int]] = {}
    grand = {"leo": 0, "meo": 0, "geo": 0, "heo": 0, "total": 0}
    for r in rows:
        code = r["owner_code"]
        cell = buckets.setdefault(code, {"leo": 0, "meo": 0, "geo": 0, "heo": 0, "total": 0})
        regime = _regime(r["apoapsis_km"], r["periapsis_km"], r["period_min"], r["eccentricity"])
        cell["total"] += 1
        grand["total"] += 1
        if regime is not None:
            key = regime.lower()
            cell[key] += 1
            grand[key] += 1

    matrix = [
        WatchlistRow(
            country_code=code,
            country_name=_owner_name(code),
            leo=c["leo"],
            meo=c["meo"],
            geo=c["geo"],
            heo=c["heo"],
            total=c["total"],
        )
        for code, c in sorted(buckets.items(), key=lambda kv: (-kv[1]["total"], kv[0]))
    ]
    total_row = WatchlistRow(
        country_code="TOTAL",
        country_name=None,
        leo=grand["leo"],
        meo=grand["meo"],
        geo=grand["geo"],
        heo=grand["heo"],
        total=grand["total"],
    )
    return matrix, total_row


async def _country_objects(conn: _Conn, owner_codes: tuple[str, ...]) -> list[dict[str, Any]]:
    """Catalog objects (with TLE lines) for one report country's owner code(s).

    Bounded to the most-recently-tracked ``_PASS_CANDIDATES_PER_COUNTRY`` rows so
    a full-catalog day stays predictable. Only rows carrying both TLE lines are
    returned (objects without elements cannot be propagated and are skipped).
    """
    return await _rows(
        conn,
        "SELECT object_id, norad_cat_id, object_name, tle_line1, tle_line2 "
        "FROM space_object "
        "WHERE decay_date IS NULL AND country_code = ANY(:codes) "
        "AND tle_line1 IS NOT NULL AND tle_line2 IS NOT NULL "
        "ORDER BY epoch DESC LIMIT :lim",
        {"codes": list(owner_codes), "lim": _PASS_CANDIDATES_PER_COUNTRY},
    )


def _passes_for_object(
    obj: dict[str, Any], start: datetime, end: datetime
) -> list[SatellitePass]:
    """Map an object's peninsula passes over [start, end] onto SatellitePass rows."""
    line1, line2 = obj.get("tle_line1"), obj.get("tle_line2")
    if not line1 or not line2:
        return []
    geometries = predict_passes(
        (line1, line2),
        KARI,
        start,
        end,
        step_s=_PASS_STEP_S,
        min_elevation_deg=_PASS_MIN_ELEVATION_DEG,
    )
    name = obj.get("object_name") or obj["object_id"]
    sat_id = str(obj.get("norad_cat_id") or obj["object_id"])
    return [
        SatellitePass(
            satellite_name=name,
            satellite_id=sat_id,
            pass_time=g.aos,
            closest_time=g.closest_time,
            closest_distance_km=g.closest_distance_km,
            azimuth_deg=g.azimuth_deg,
            elevation_deg=g.elevation_deg,
        )
        for g in geometries
    ]


async def _country_activity(
    conn: _Conn, start: datetime, end: datetime
) -> list[CountryActivity]:
    """§2/§3 — peninsula passes per report country (북한 / 중·러·일)."""
    activity: list[CountryActivity] = []
    for country in ReportCountry:
        objects = await _country_objects(conn, _REPORT_COUNTRY_OWNER_CODES[country])
        passes: list[SatellitePass] = []
        for obj in objects:
            passes.extend(_passes_for_object(obj, start, end))
            if len(passes) >= _PASS_MAX_PASSES_PER_COUNTRY:
                passes = passes[:_PASS_MAX_PASSES_PER_COUNTRY]
                break
        passes.sort(key=lambda p: p.pass_time)
        activity.append(
            CountryActivity(
                country_code=country.value,
                country_name=_REPORT_COUNTRY_NAMES[country],
                passes=passes,
            )
        )
    return activity


async def _conjunctions(conn: _Conn, start: datetime, end: datetime) -> list[ConjunctionRow]:
    """§4 — close approaches whose TCA falls inside the report day."""
    rows = await _rows(
        conn,
        "SELECT primary_name, secondary_name, miss_distance_km, probability, tca, "
        "       severity::text AS severity "
        "FROM conjunction WHERE tca >= :start AND tca < :end ORDER BY tca ASC",
        {"start": start, "end": end},
    )
    return [
        ConjunctionRow(
            satellite_name=r["primary_name"],
            object_name=r["secondary_name"],
            tca=r["tca"],
            distance_km=float(r["miss_distance_km"]),
            probability=float(r["probability"]) if r["probability"] is not None else None,
            risk_category=r["severity"],
        )
        for r in rows
    ]


async def _debris(conn: _Conn) -> list[dict[str, Any]]:
    """§5 — live DEBRIS-class catalog rows with the fields the risk model needs."""
    return await _rows(
        conn,
        "SELECT object_id, object_name, country_code, rcs_size, "
        "       apoapsis_km, periapsis_km, period_min "
        "FROM space_object WHERE decay_date IS NULL AND object_type::text = 'DEBRIS'",
    )


def _debris_level(row: dict[str, Any]) -> str | None:
    """Risk level (Critical/High/Medium/Low) for one debris row, or None.

    Reuses ``debris_risk.risk_score`` / ``risk_level`` over the mean shell
    altitude (apside-derived) and the circular-orbit speed at that altitude. A
    row with no derivable altitude cannot be scored and is skipped.
    """
    mean_alt = _mean_altitude_km(row.get("apoapsis_km"), row.get("periapsis_km"))
    if mean_alt is None:
        return None
    score = risk_score(mean_alt, circular_speed_km_s(mean_alt), row.get("rcs_size"))
    return risk_level(score)


async def _debris_risk(
    conn: _Conn,
) -> tuple[DebrisRiskCounts, list[HighRiskDebrisRow], list[float]]:
    """§5a counts + §5c high-risk table + §5b altitude set from the live debris catalog.

    The third return value is the mean shell altitude of every *scored* debris row
    (those with a derivable altitude), feeding the §5b 고도별 잔해 밀도 chart. It is
    the SAME selection counted in ``DebrisRiskCounts`` so the chart and counts agree.
    """
    rows = await _debris(conn)
    counts = {"critical": 0, "high": 0, "moderate": 0, "low": 0}
    scored: list[tuple[str, dict[str, Any]]] = []
    altitudes: list[float] = []
    field_for = {"Critical": "critical", "High": "high", "Medium": "moderate", "Low": "low"}
    for row in rows:
        level = _debris_level(row)
        if level is None:
            continue
        counts[field_for[level]] += 1
        mean_alt = _mean_altitude_km(row.get("apoapsis_km"), row.get("periapsis_km"))
        if mean_alt is not None:
            altitudes.append(mean_alt)
        if level in _HIGH_RISK_LEVELS:
            scored.append((level, row))

    # Highest grade first (Critical before High); cap the table length.
    scored.sort(key=lambda lr: _HIGH_RISK_LEVELS.index(lr[0]))
    high_risk = [
        HighRiskDebrisRow(
            country_code=row.get("country_code") or "UNKNOWN",
            country_name=_owner_name(row.get("country_code")),
            debris_name=row.get("object_name") or row["object_id"],
            risk_grade=_RISK_KO[level],
            rcs_size=row.get("rcs_size"),
            mean_altitude_km=_mean_altitude_km(row.get("apoapsis_km"), row.get("periapsis_km")),
            period_min=row.get("period_min"),
            perigee_km=row.get("periapsis_km"),
            apogee_km=row.get("apoapsis_km"),
        )
        for level, row in scored[:_HIGH_RISK_DEBRIS_LIMIT]
    ]
    return (
        DebrisRiskCounts(
            critical=counts["critical"],
            high=counts["high"],
            moderate=counts["moderate"],
            low=counts["low"],
        ),
        high_risk,
        altitudes,
    )


async def assemble_daily(
    report_date: date,
    conn: _Conn,
    *,
    settings: Settings | None = None,
) -> DailyReportPayload:
    """Assemble the deterministic payload for one day's space-operations report.

    ``conn`` is an injected SQLAlchemy async connection (caller-owned). Raises
    ``ValueError`` for a future ``report_date``; any day with no data returns a
    valid payload with empty sections. Objects missing TLE lines are skipped in
    the pass pass rather than crashing it.

    ``settings`` is accepted for signature stability with the rest of the report
    pipeline; the deterministic data assembly takes no tunables from it (the pass
    mask / cost caps are module constants), so it is currently unused.
    """
    _ = settings
    if report_date > datetime.now(UTC).date():
        raise ValueError(f"report_date {report_date.isoformat()} is in the future")

    start, end = _day_window(report_date)
    watchlist_matrix, watchlist_total = await _watchlist(conn)
    country_activity = await _country_activity(conn, start, end)
    conjunctions = await _conjunctions(conn, start, end)
    debris_risk_counts, high_risk_debris, debris_altitudes = await _debris_risk(conn)

    return DailyReportPayload(
        report_date=report_date,
        watchlist_matrix=watchlist_matrix,
        watchlist_total=watchlist_total,
        country_activity=country_activity,
        conjunctions=conjunctions,
        debris_risk_counts=debris_risk_counts,
        high_risk_debris=high_risk_debris,
        debris_altitudes_km=debris_altitudes,
    )
