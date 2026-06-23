"""Daily report assembler: payload assembly over a fake connection (unit) plus an
infra-gated round-trip against the real schema.

The assembler takes an *injected* async connection (the engine read primitive,
``get_engine().connect()``). Postgres is not assumed available in CI/dev here, so
the branch-coverage tests drive it with ``_FakeConn`` — a minimal stub matching
the ``await conn.execute(text, params)`` -> ``result.mappings()`` contract the
``repository`` module uses. A final test seeds the real schema when Postgres is up
(mirrors ``test_gp_history``'s ``infra_up`` skip pattern).

The §2/§3 pass tests use a real ISS TLE whose epoch (2024-070) sits on
``PASS_DATE`` so ``predict_passes`` over that UTC day yields well-formed passes
over 대전 KARI; the object is attributed to an NK/CN owner code so the assembler
routes it into ``country_activity``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from orbital_engine import db, state
from orbital_engine.config import Settings
from orbital_engine.domain.space_object import SpaceObject
from orbital_engine.reports.assembler import assemble_daily
from orbital_engine.reports.schemas import DailyReportPayload, ReportCountry

REPORT_DATE = date(2026, 6, 20)
DAY_START = datetime(2026, 6, 20, tzinfo=UTC)

# A real ISS element set (epoch 2024-070, 10 Mar 2024). Propagated over PASS_DATE
# it makes several KARI passes above a 10-deg mask (verified: 4 passes).
PASS_DATE = date(2024, 3, 10)
ISS_L1 = "1 25544U 98067A   24070.51782407  .00006484  00000-0  12035-3 0  9993"
ISS_L2 = "2 25544  51.6439  32.1281 0006008  76.8618  58.0505 15.50079139442263"


# --- Fake connection --------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def mappings(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeConn:
    """Dispatches each query (by SQL substring) to a seeded row set.

    ``tables`` keys: ``watchlist`` (all live catalog rows), ``country`` (owner_code
    -> object rows, returned for that country's ANY(:codes)), ``conjunctions``,
    and ``debris``. The country query is filtered by the bound ``codes`` param,
    matching the real ``country_code = ANY(:codes)`` SQL.
    """

    def __init__(self, tables: dict[str, Any]):
        self.tables = tables
        self.calls: list[str] = []

    async def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> _FakeResult:
        sql = str(statement)
        self.calls.append(sql)
        params = parameters or {}
        if "country_code = ANY(:codes)" in sql:
            by_code: dict[str, list[dict[str, Any]]] = self.tables.get("country", {})
            rows: list[dict[str, Any]] = []
            for code in params.get("codes", []):
                rows.extend(by_code.get(code, []))
            return _FakeResult(rows)
        if "FROM conjunction" in sql:
            return _FakeResult(self.tables.get("conjunctions", []))
        if "object_type::text = 'DEBRIS'" in sql:
            return _FakeResult(self.tables.get("debris", []))
        if "FROM space_object WHERE decay_date IS NULL" in sql:
            return _FakeResult(self.tables.get("watchlist", []))
        raise AssertionError(f"unexpected query: {sql}")


def _wl_row(owner_code: str | None, **over: Any) -> dict[str, Any]:
    """One watchlist (live-catalog) row. Defaults to a LEO orbit."""
    row = {
        "owner_code": owner_code or "UNKNOWN",
        "apoapsis_km": 420.0,
        "periapsis_km": 410.0,
        "period_min": 92.0,
        "eccentricity": 0.0006,
    }
    row.update(over)
    return row


def _sat_row(object_id: str, name: str, l1: str, l2: str, **over: Any) -> dict[str, Any]:
    row = {
        "object_id": object_id,
        "norad_cat_id": 25544,
        "object_name": name,
        "tle_line1": l1,
        "tle_line2": l2,
    }
    row.update(over)
    return row


def _debris_row(object_id: str, name: str, **over: Any) -> dict[str, Any]:
    row = {
        "object_id": object_id,
        "object_name": name,
        "country_code": "PRC",
        "rcs_size": "LARGE",
        "apoapsis_km": 850.0,  # primary LEO debris peak -> high density factor
        "periapsis_km": 850.0,
        "period_min": 102.0,
    }
    row.update(over)
    return row


# --- §1 watchlist matrix ----------------------------------------------------


async def test_watchlist_matrix_groups_by_country_and_regime() -> None:
    watchlist = [
        _wl_row("PRC"),  # LEO
        _wl_row("PRC", apoapsis_km=20200.0, periapsis_km=20180.0, period_min=718.0),  # MEO
        _wl_row("CIS", apoapsis_km=35786.0, periapsis_km=35780.0, period_min=1436.0),  # GEO
        _wl_row("CIS", eccentricity=0.7, apoapsis_km=39000.0, periapsis_km=600.0),  # HEO
        _wl_row(None, apoapsis_km=None, periapsis_km=None, period_min=None),  # undeterminable
    ]
    conn = _FakeConn({"watchlist": watchlist})
    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())

    by_code = {r.country_code: r for r in payload.watchlist_matrix}
    assert by_code["PRC"].leo == 1 and by_code["PRC"].meo == 1 and by_code["PRC"].total == 2
    assert by_code["PRC"].country_name == "중국"
    assert by_code["CIS"].geo == 1 and by_code["CIS"].heo == 1 and by_code["CIS"].total == 2
    # Undeterminable regime: counted in the row total, not in any regime column.
    assert by_code["UNKNOWN"].total == 1
    assert by_code["UNKNOWN"].leo == by_code["UNKNOWN"].meo == 0
    assert by_code["UNKNOWN"].geo == by_code["UNKNOWN"].heo == 0
    assert by_code["UNKNOWN"].country_name is None

    total = payload.watchlist_total
    assert total is not None and total.country_code == "TOTAL"
    assert total.leo == 1 and total.meo == 1 and total.geo == 1 and total.heo == 1
    assert total.total == 5  # every object counted, incl. the undeterminable one


# --- §2/§3 country activity (passes) ----------------------------------------


async def test_country_activity_yields_passes_for_nk_object() -> None:
    nk_sat = _sat_row("SH:CAT:000025544", "KMS-4", ISS_L1, ISS_L2)
    conn = _FakeConn({"country": {"PRK": [nk_sat]}})
    payload = await assemble_daily(PASS_DATE, conn, settings=Settings())

    by_country = {a.country_code: a for a in payload.country_activity}
    # All four report countries are always present (empty where no passes).
    assert set(by_country) == {c.value for c in ReportCountry}
    nk = by_country[ReportCountry.NORTH_KOREA.value]
    assert nk.country_name == "북한"
    assert len(nk.passes) >= 1
    p = nk.passes[0]
    assert p.satellite_name == "KMS-4"
    assert p.satellite_id == "25544"
    assert p.elevation_deg is not None and p.elevation_deg >= 10.0  # mask honored
    assert p.closest_distance_km is not None and p.closest_distance_km > 0.0
    # Passes are sorted by pass_time and fall inside the report day.
    times = [pp.pass_time for pp in nk.passes]
    assert times == sorted(times)
    day_start = datetime(PASS_DATE.year, PASS_DATE.month, PASS_DATE.day, tzinfo=UTC)
    assert all(day_start <= t < day_start + timedelta(days=1) for t in times)
    # The other report countries had no objects -> empty.
    assert by_country[ReportCountry.JAPAN.value].passes == []


async def test_country_activity_skips_objects_without_tle() -> None:
    # A CN object missing its TLE lines is skipped gracefully (no crash, no pass).
    no_tle = _sat_row("SH:CAT:000000001", "NO-TLE", ISS_L1, ISS_L2, tle_line1=None, tle_line2=None)
    conn = _FakeConn({"country": {"PRC": [no_tle]}})
    payload = await assemble_daily(PASS_DATE, conn, settings=Settings())
    cn = next(a for a in payload.country_activity if a.country_code == ReportCountry.CHINA.value)
    assert cn.passes == []


# --- §4 conjunctions --------------------------------------------------------


async def test_conjunctions_map_in_window() -> None:
    conn = _FakeConn(
        {
            "conjunctions": [
                {
                    "primary_name": "SAT-A",
                    "secondary_name": "DEBRIS-B",
                    "miss_distance_km": 0.8,
                    "probability": 1e-3,
                    "tca": DAY_START + timedelta(hours=12),
                    "severity": "HIGH",
                },
                {
                    "primary_name": "SAT-C",
                    "secondary_name": "SAT-D",
                    "miss_distance_km": 4.2,
                    "probability": None,  # missing Pc still renders
                    "tca": DAY_START + timedelta(hours=3),
                    "severity": "MOD",
                },
            ]
        }
    )
    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())
    assert len(payload.conjunctions) == 2
    first = payload.conjunctions[0]
    assert first.satellite_name == "SAT-A" and first.object_name == "DEBRIS-B"
    assert first.distance_km == 0.8 and first.probability == 1e-3
    assert first.risk_category == "HIGH"
    assert payload.conjunctions[1].probability is None


# --- §5 debris risk ---------------------------------------------------------


async def test_debris_risk_counts_and_high_risk_table() -> None:
    debris = [
        # 850 km + LARGE -> density 1.0, speed ~7.4 => high score (Critical).
        _debris_row("SH:CAT:000000010", "FENGYUN-1C DEB", country_code="PRC"),
        # 850 km + SMALL -> lower size factor => Medium-ish, not high-risk.
        _debris_row("SH:CAT:000000011", "SMALL DEB", rcs_size="SMALL"),
        # No apsides -> cannot score -> skipped entirely.
        _debris_row("SH:CAT:000000012", "NO-ORBIT DEB", apoapsis_km=None, periapsis_km=None),
    ]
    conn = _FakeConn({"debris": debris})
    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())

    counts = payload.debris_risk_counts
    total = counts.critical + counts.high + counts.moderate + counts.low
    assert total == 2  # the un-scorable row is excluded from the counts
    assert counts.critical >= 1  # the LARGE 850 km fragment

    assert len(payload.high_risk_debris) >= 1
    top = payload.high_risk_debris[0]
    assert top.debris_name == "FENGYUN-1C DEB"
    assert top.country_code == "PRC" and top.country_name == "중국"
    assert top.risk_grade in {"심각", "높음"}
    assert top.rcs_size == "LARGE"
    assert top.mean_altitude_km == 850.0
    assert top.perigee_km == 850.0 and top.apogee_km == 850.0
    assert top.period_min == 102.0
    # The SMALL fragment is not in the high-risk (Critical/High) table.
    assert all(r.debris_name != "SMALL DEB" for r in payload.high_risk_debris)

    # §5b altitude set: one mean altitude per SCORED row (same selection as the
    # counts) — the two scorable rows at 850 km, and NOT the un-scorable one.
    assert payload.debris_altitudes_km == [850.0, 850.0]


# --- Empty day --------------------------------------------------------------


async def test_empty_day_yields_valid_empty_payload() -> None:
    conn = _FakeConn({})  # every query returns []
    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())
    assert isinstance(payload, DailyReportPayload)
    assert payload.report_date == REPORT_DATE
    assert payload.watchlist_matrix == []
    # An empty catalog still yields a TOTAL row (all zeros).
    assert payload.watchlist_total is not None
    assert payload.watchlist_total.total == 0
    # All four countries present, every section empty.
    assert len(payload.country_activity) == len(ReportCountry)
    assert all(a.passes == [] for a in payload.country_activity)
    assert payload.conjunctions == []
    assert payload.debris_risk_counts.critical == 0
    assert payload.debris_risk_counts.low == 0
    assert payload.high_risk_debris == []
    assert payload.debris_altitudes_km == []


# --- Owner-name / regime branches -------------------------------------------


@pytest.mark.parametrize(
    ("apo", "peri", "period", "ecc", "expected"),
    [
        (420.0, 410.0, 92.0, 0.0006, "LEO"),
        (20200.0, 20180.0, 718.0, 0.001, "MEO"),
        (35786.0, 35780.0, 1436.0, 0.0002, "GEO"),
        (39000.0, 600.0, 690.0, 0.7, "HEO"),  # high eccentricity wins
        (None, None, 1436.0, 0.0, "GEO"),  # period-only GEO fallback
        (None, None, None, None, None),  # nothing derivable
    ],
)
async def test_regime_classification(
    apo: float | None,
    peri: float | None,
    period: float | None,
    ecc: float | None,
    expected: str | None,
) -> None:
    row_in = _wl_row("PRC", apoapsis_km=apo, periapsis_km=peri, period_min=period, eccentricity=ecc)
    conn = _FakeConn({"watchlist": [row_in]})
    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())
    row = payload.watchlist_matrix[0]
    # Exactly the expected regime column is incremented (or none for None).
    cols = {"LEO": row.leo, "MEO": row.meo, "GEO": row.geo, "HEO": row.heo}
    if expected is None:
        assert sum(cols.values()) == 0 and row.total == 1
    else:
        assert cols[expected] == 1 and sum(cols.values()) == 1


async def test_unmapped_owner_code_passes_through_without_name() -> None:
    conn = _FakeConn({"watchlist": [_wl_row("XYZ")]})
    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())
    row = payload.watchlist_matrix[0]
    assert row.country_code == "XYZ" and row.country_name is None


# --- Future / today date guard ----------------------------------------------


async def test_future_date_raises_value_error() -> None:
    future = datetime.now(UTC).date() + timedelta(days=1)
    with pytest.raises(ValueError, match="future"):
        await assemble_daily(future, _FakeConn({}), settings=Settings())


async def test_today_is_allowed() -> None:
    today = datetime.now(UTC).date()
    payload = await assemble_daily(today, _FakeConn({}), settings=Settings())
    assert payload.report_date == today


# --- Infra-gated round-trip against the real schema -------------------------


@pytest.fixture
async def infra_up() -> bool:
    if not (await db.ping() and await state.ping()):
        pytest.skip("Postgres/Redis not available — skipping assembler round-trip")
    return True


_RT_OBJ = SpaceObject.model_validate(
    {
        "OBJECT_NAME": "ISS (ZARYA)",
        "OBJECT_ID": "1998-067A",
        "NORAD_CAT_ID": 25544,
        "OBJECT_TYPE": "PAYLOAD",
        "COUNTRY_CODE": "PRC",
        "EPOCH": "2024-03-10T12:25:00",
        "MEAN_MOTION": 15.50079139,
        "ECCENTRICITY": 0.0006008,
        "INCLINATION": 51.6439,
        "RA_OF_ASC_NODE": 32.1281,
        "ARG_OF_PERICENTER": 76.8618,
        "MEAN_ANOMALY": 58.0505,
        "APOAPSIS": 420.0,
        "PERIAPSIS": 410.0,
        "TLE_LINE1": ISS_L1,
        "TLE_LINE2": ISS_L2,
    }
)


async def test_assemble_daily_round_trip(infra_up: bool) -> None:
    # Proves every query in assemble_daily runs against the REAL migrated schema
    # (column-name / ANY(:codes) bugs the fake conn cannot catch) and yields a
    # valid, internally-consistent payload.
    from orbital_engine.repository import upsert_objects

    await upsert_objects([_RT_OBJ])
    async with db.get_engine().connect() as conn:
        payload = await assemble_daily(PASS_DATE, conn, settings=Settings())

    assert isinstance(payload, DailyReportPayload)
    assert payload.report_date == PASS_DATE
    # The catalog has at least the seeded PRC object => non-empty watchlist.
    assert payload.watchlist_total is not None and payload.watchlist_total.total >= 1
    assert len(payload.country_activity) == len(ReportCountry)
    # Risk counts are internally consistent (non-negative ints).
    c = payload.debris_risk_counts
    assert min(c.critical, c.high, c.moderate, c.low) >= 0
    await db.dispose()
    await state.close()
