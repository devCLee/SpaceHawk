"""Daily report assembler: payload assembly over a fake connection (unit) plus an
infra-gated round-trip against the real schema.

The assembler takes an *injected* async connection (the engine read primitive,
``get_engine().connect()``). Postgres is not assumed available in CI/dev here, so
the branch-coverage tests drive it with ``_FakeConn`` — a minimal stub matching
the ``await conn.execute(text, params)`` -> ``result.mappings()`` contract the
``repository`` module uses. A final test seeds the real schema when Postgres is up
(mirrors ``test_gp_history``'s ``infra_up`` skip pattern).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from orbital_engine import db, state
from orbital_engine.config import Settings
from orbital_engine.domain.space_object import SpaceObject
from orbital_engine.reports.assembler import assemble_daily
from orbital_engine.reports.schemas import DailyReportPayload, ManeuverDataStatus
from orbital_engine.repository import append_history, upsert_objects

REPORT_DATE = date(2026, 6, 20)
DAY_START = datetime(2026, 6, 20, tzinfo=UTC)


# --- Fake connection --------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def mappings(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeConn:
    """Dispatches each query (by SQL substring) to a seeded row set.

    ``tables`` keys: ``category_counts``, ``payloads``, ``conjunctions``,
    ``reentries``, ``country_counts``, and ``history`` (object_id -> rows). The
    history query is filtered by the bound ``oid`` param, matching the real SQL.
    """

    def __init__(self, tables: dict[str, Any]):
        self.tables = tables
        self.calls: list[str] = []

    async def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> _FakeResult:
        sql = str(statement)
        self.calls.append(sql)
        params = parameters or {}
        if "GROUP BY object_type" in sql:
            return _FakeResult(self.tables.get("category_counts", []))
        if "object_type::text = 'PAYLOAD'" in sql:
            return _FakeResult(self.tables.get("payloads", []))
        if "FROM conjunction" in sql:
            return _FakeResult(self.tables.get("conjunctions", []))
        if "FROM gp_history" in sql:
            rows = self.tables.get("history", {}).get(params.get("oid"), [])
            return _FakeResult(rows)
        if "decay_date = :d" in sql:
            return _FakeResult(self.tables.get("reentries", []))
        if "GROUP BY owner_code" in sql:
            return _FakeResult(self.tables.get("country_counts", []))
        raise AssertionError(f"unexpected query: {sql}")


def _payload_row(object_id: str, name: str, **over: Any) -> dict[str, Any]:
    row = {
        "object_id": object_id,
        "norad_cat_id": 25544,
        "object_name": name,
        "country_code": "US",
        "object_type": "PAYLOAD",
        "apoapsis_km": 420.0,
        "periapsis_km": 410.0,
        "period_min": 92.0,
    }
    row.update(over)
    return row


def _hist_row(object_id: str, days: int, sma: float, **over: Any) -> dict[str, Any]:
    # Mirrors the real gp_history projection: no object_name / norad_cat_id columns.
    row = {
        "object_id": object_id,
        "epoch": DAY_START - timedelta(days=days),
        "mean_motion": 15.5,
        "eccentricity": 0.0006,
        "inclination": 51.6,
        "ra_of_asc_node": 32.0,
        "semimajor_axis_km": sma,
        "apoapsis_km": sma - 6378.0 + 10.0,
        "periapsis_km": sma - 6378.0 - 10.0,
    }
    row.update(over)
    return row


# --- Happy path -------------------------------------------------------------


async def test_happy_path_populates_every_section() -> None:
    oid = "SH:CAT:000025544"
    # >= 4 epochs with an injected +5 km step => detect_maneuvers flags one burn.
    smas = [6790.0, 6789.9, 6789.8, 6794.8, 6794.7]
    history = [_hist_row(oid, days=10 - i, sma=s) for i, s in enumerate(smas)]
    conn = _FakeConn(
        {
            "category_counts": [
                {"object_type": "PAYLOAD", "n": 2},
                {"object_type": "DEBRIS", "n": 1},
            ],
            "payloads": [_payload_row(oid, "ISS (ZARYA)")],
            "conjunctions": [
                {
                    "id": "SCR:A:B:20260620T1200",
                    "primary_object_id": "SH:CAT:000000001",
                    "primary_name": "SAT-A",
                    "secondary_object_id": "SH:CAT:000000002",
                    "secondary_name": "SAT-B",
                    "miss_distance_km": 0.8,
                    "probability": 1e-3,
                    "tca": DAY_START + timedelta(hours=12),
                    "severity": "HIGH",
                }
            ],
            "reentries": [
                {
                    "object_id": "SH:CAT:000099999",
                    "norad_cat_id": 99999,
                    "object_name": "OLD ROCKET",
                    "country_code": "PRC",
                }
            ],
            "country_counts": [
                {"owner_code": "US", "n": 2},
                {"owner_code": "UNKNOWN", "n": 1},
            ],
            "history": {oid: history},
        }
    )

    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())

    assert isinstance(payload, DailyReportPayload)
    assert payload.report_date == REPORT_DATE
    # §1 categories: Korean names mapped, debris counted.
    assert {c.category: c.count for c in payload.surveillance_categories} == {
        "위성(탑재체)": 2,
        "파편": 1,
    }
    # §1 notable object: owner resolved, regime LEO.
    assert len(payload.surveillance_objects) == 1
    obj = payload.surveillance_objects[0]
    assert obj.owner_code == "US" and obj.owner_name == "미국"
    assert obj.regime == "LEO"
    # §2 conjunction in-window.
    assert len(payload.conjunctions) == 1
    assert payload.conjunctions[0].alert_level == "HIGH"
    # §3 maneuver: sufficient history => PRESENT, a burn detected.
    assert len(payload.maneuvers) == 1
    mnv = payload.maneuvers[0]
    assert mnv.status is ManeuverDataStatus.PRESENT
    assert mnv.history_epochs == 5
    assert mnv.delta_sma_km is not None and mnv.delta_sma_km > 4.9
    assert mnv.classification is not None
    assert mnv.epoch is not None
    # §4 reentry window = the report day.
    assert len(payload.reentries) == 1
    assert payload.reentries[0].owner_code == "PRC"
    assert payload.reentries[0].predicted_window_start == DAY_START
    assert payload.reentries[0].predicted_window_end == DAY_START + timedelta(days=1)
    # §5 country breakdown: unknown bucket resolves to no name.
    codes = {c.owner_code: c.owner_name for c in payload.country_breakdown}
    assert codes["US"] == "미국" and codes["UNKNOWN"] is None
    # Charts: one series with all epochs.
    assert len(payload.time_series) == 1
    assert len(payload.time_series[0].points) == 5
    assert payload.time_series[0].points[0].apogee_km is not None


# --- Empty day --------------------------------------------------------------


async def test_empty_day_yields_valid_empty_payload() -> None:
    conn = _FakeConn({})  # every query returns []
    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())
    assert payload.report_date == REPORT_DATE
    assert payload.surveillance_categories == []
    assert payload.surveillance_objects == []
    assert payload.conjunctions == []
    assert payload.maneuvers == []
    assert payload.reentries == []
    assert payload.country_breakdown == []
    assert payload.time_series == []


# --- Partial: insufficient history -----------------------------------------


async def test_object_with_too_few_epochs_marked_insufficient() -> None:
    oid = "SH:CAT:000025544"
    history = [_hist_row(oid, days=3 - i, sma=6790.0) for i in range(3)]  # 3 < 4
    conn = _FakeConn(
        {
            "payloads": [_payload_row(oid, "ISS (ZARYA)")],
            "history": {oid: history},
        }
    )
    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())
    assert len(payload.maneuvers) == 1
    mnv = payload.maneuvers[0]
    assert mnv.status is ManeuverDataStatus.INSUFFICIENT_HISTORY
    assert mnv.history_epochs == 3
    assert mnv.classification is None and mnv.delta_v_m_s is None and mnv.epoch is None


async def test_sufficient_history_but_no_maneuver_flagged() -> None:
    oid = "SH:CAT:000025544"
    # 5 epochs of smooth drag: PRESENT but detect_maneuvers returns nothing.
    history = [_hist_row(oid, days=5 - i, sma=6790.0 - 0.1 * i) for i in range(5)]
    conn = _FakeConn({"payloads": [_payload_row(oid, "ISS")], "history": {oid: history}})
    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())
    mnv = payload.maneuvers[0]
    assert mnv.status is ManeuverDataStatus.PRESENT
    assert mnv.classification is None and mnv.delta_sma_km is None and mnv.epoch is None


# --- Regime + owner-name branches -------------------------------------------


@pytest.mark.parametrize(
    ("apo", "peri", "period", "expected"),
    [
        (420.0, 410.0, 92.0, "LEO"),
        (20200.0, 20180.0, 718.0, "MEO"),
        (35786.0, 35780.0, 1436.0, "GEO"),
        (35000.0, 500.0, 600.0, "HEO"),
        (None, None, None, None),
    ],
)
async def test_regime_classification(
    apo: float | None, peri: float | None, period: float | None, expected: str | None
) -> None:
    oid = "SH:CAT:000000001"
    conn = _FakeConn(
        {"payloads": [_payload_row(oid, "X", apoapsis_km=apo, periapsis_km=peri, period_min=period)]}
    )
    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())
    assert payload.surveillance_objects[0].regime == expected


async def test_unknown_owner_code_passes_through_without_name() -> None:
    oid = "SH:CAT:000000001"
    conn = _FakeConn({"payloads": [_payload_row(oid, "X", country_code="XYZ")]})
    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())
    obj = payload.surveillance_objects[0]
    assert obj.owner_code == "XYZ" and obj.owner_name is None


async def test_null_country_code_yields_no_owner() -> None:
    oid = "SH:CAT:000000001"
    conn = _FakeConn({"payloads": [_payload_row(oid, "X", country_code=None)]})
    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())
    assert payload.surveillance_objects[0].owner_name is None


async def test_unmapped_object_type_category_falls_back_to_raw() -> None:
    conn = _FakeConn({"category_counts": [{"object_type": "WIDGET", "n": 3}]})
    payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())
    assert payload.surveillance_categories[0].category == "WIDGET"


# --- Future date ------------------------------------------------------------


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
        "COUNTRY_CODE": "US",
        "EPOCH": "2026-06-19T12:00:00",
        "MEAN_MOTION": 15.50079139,
        "ECCENTRICITY": 0.0006008,
        "INCLINATION": 51.6439,
        "RA_OF_ASC_NODE": 32.1281,
        "ARG_OF_PERICENTER": 76.8618,
        "MEAN_ANOMALY": 58.0505,
        "APOAPSIS": 420.0,
        "PERIAPSIS": 410.0,
    }
)


async def test_assemble_daily_round_trip(infra_up: bool) -> None:
    # Proves every query in assemble_daily runs against the REAL migrated schema
    # (the column-name bug the fake conn could not catch) and yields a valid,
    # internally-consistent payload. The seeded object guarantees >= 1 payload row,
    # but a populated dev catalog may push it past the notable-object LIMIT, so we
    # assert structural validity rather than its presence in the top-N.
    await upsert_objects([_RT_OBJ])
    await append_history([_RT_OBJ])
    async with db.get_engine().connect() as conn:
        payload = await assemble_daily(REPORT_DATE, conn, settings=Settings())

    assert isinstance(payload, DailyReportPayload)
    assert payload.report_date == REPORT_DATE
    # One maneuver entry + one chart series per notable object.
    assert len(payload.maneuvers) == len(payload.surveillance_objects)
    assert len(payload.time_series) == len(payload.surveillance_objects)
    # The catalog has payloads, so the §1 category table is non-empty.
    assert any(c.count > 0 for c in payload.surveillance_categories)
    # Every maneuver entry is one of the two valid statuses (no crash on partial
    # history): real catalog objects mostly have < 4 epochs => "정보 없음".
    assert all(m.status in ManeuverDataStatus for m in payload.maneuvers)
    await db.dispose()
    await state.close()
