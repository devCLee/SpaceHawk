"""Composite threat-score endpoint consumed by the web BFF (mentoring #11 / S2).

``GET /scores`` rolls the five analysis methods (maneuver detection,
conjunction screening, RPO monitoring, debris risk, behavioral-baseline
anomalies) into one ranked, per-object 0-100 composite. Every item carries its
normalized per-method components and the response carries the weights, so any
composite is recomputable by hand (``scoring`` module docstring has the
formulas). ``GET /scores/history`` replays the same rollup with the event
window anchored at each of the last N days, yielding the threat-level
histogram over time (the dashboard trend chart). Both sit in
``MANEUVER_INTEL`` — the composite mixes maneuver intelligence, so it
inherits that domain's analyst-tier floor.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from orbital_engine.api.debris import _enrich
from orbital_engine.debris_risk import risk_level
from orbital_engine.repository import (
    query_debris,
    score_anomaly_aggregates,
    score_conjunction_aggregates,
    score_maneuver_aggregates,
    score_rpo_aggregates,
)
from orbital_engine.scoring import (
    DEBRIS_STANDALONE_MIN,
    WEIGHTS,
    anomaly_component,
    composite_score,
    conjunction_component,
    debris_component,
    maneuver_component,
    rpo_component,
)
from orbital_engine.security.attributes import Action, DataDomain, Subject
from orbital_engine.security.enforce import requires

router = APIRouter(tags=["scores"])


class ScoreComponents(BaseModel):
    """Normalized 0..1 per-method scores; None = no signal in the window."""

    maneuver: float | None = None
    conjunction: float | None = None
    rpo: float | None = None
    debris: float | None = None
    anomaly: float | None = None


class ScoreRaw(BaseModel):
    """Underlying raw evidence for drill-down/tooltips."""

    max_confidence: float | None = None
    max_delta_v_m_s: float | None = None
    maneuver_count: int | None = None
    max_pc: float | None = None
    min_miss_km: float | None = None
    severity: str | None = None
    conjunction_count: int | None = None
    max_coplanarity: float | None = None
    rpo_count: int | None = None
    debris_risk_score: float | None = None
    max_delta_v_sigma: float | None = None
    novel_type: bool | None = None
    anomaly_count: int | None = None


class ScoreItem(BaseModel):
    """One object's composite threat score with its explainable breakdown."""

    object_id: str
    object_name: str
    composite: float
    level: str
    components: ScoreComponents
    raw: ScoreRaw


class ScoreSummary(BaseModel):
    """Population rollup for the dashboard KPI tiles."""

    total: int
    by_level: dict[str, int] = Field(default_factory=dict)
    by_method: dict[str, int] = Field(default_factory=dict)


class ScoresResponse(BaseModel):
    generated_at: datetime
    window_days: int
    weights: dict[str, float]
    summary: ScoreSummary
    items: list[ScoreItem]


class ScoreHistoryPoint(BaseModel):
    """Threat-level histogram of the scored population at one past day."""

    date: date
    by_level: dict[str, int] = Field(default_factory=dict)


class ScoresHistoryResponse(BaseModel):
    window_days: int
    days: int
    points: list[ScoreHistoryPoint]


def _entry(store: dict[str, dict[str, Any]], object_id: str) -> dict[str, Any]:
    return store.setdefault(object_id, {"name": None, "components": {}, "raw": {}})


async def _assemble_items(
    window_days: int,
    *,
    as_of: datetime | None = None,
    debris_rows: list[dict[str, Any]] | None = None,
) -> list[ScoreItem]:
    """Score the population with the event window ending at ``as_of`` (now).

    ``debris_rows`` lets /scores/history fetch+enrich debris once — the debris
    component reflects current catalog state (no event history), so it is
    anchor-invariant by construction.
    """
    objects: dict[str, dict[str, Any]] = {}

    # Name precedence: maneuver > conjunction > debris > alert payloads —
    # processing order sets the first (most authoritative) name that exists.
    for row in await score_maneuver_aggregates(window_days=window_days, as_of=as_of):
        e = _entry(objects, row["object_id"])
        e["name"] = e["name"] or row.get("object_name")
        if row.get("max_confidence") is not None:
            e["components"]["maneuver"] = maneuver_component(row["max_confidence"])
        e["raw"].update(
            max_confidence=row.get("max_confidence"),
            max_delta_v_m_s=row.get("max_delta_v_m_s"),
            maneuver_count=row["event_count"],
        )

    for row in await score_conjunction_aggregates(window_days=window_days, as_of=as_of):
        e = _entry(objects, row["object_id"])
        e["name"] = e["name"] or row.get("object_name")
        component = conjunction_component(row.get("max_pc"), row.get("severity"))
        if component is not None:
            e["components"]["conjunction"] = component
        e["raw"].update(
            max_pc=row.get("max_pc"),
            min_miss_km=row.get("min_miss_km"),
            severity=row.get("severity"),
            conjunction_count=row["event_count"],
        )

    if debris_rows is None:
        debris_rows = [_enrich(r) for r in await query_debris(limit=20000)]
    for row in debris_rows:
        e = _entry(objects, row["object_id"])
        e["name"] = e["name"] or row.get("object_name")
        e["components"]["debris"] = debris_component(row["risk_score"])
        e["raw"].update(debris_risk_score=row["risk_score"])

    for row in await score_rpo_aggregates(window_days=window_days, as_of=as_of):
        e = _entry(objects, row["object_id"])
        e["name"] = e["name"] or row.get("object_name")
        if row.get("max_coplanarity") is not None:
            e["components"]["rpo"] = rpo_component(row["max_coplanarity"])
        e["raw"].update(
            max_coplanarity=row.get("max_coplanarity"),
            rpo_count=row["event_count"],
        )

    for row in await score_anomaly_aggregates(window_days=window_days, as_of=as_of):
        e = _entry(objects, row["object_id"])
        e["name"] = e["name"] or row.get("object_name")
        e["components"]["anomaly"] = anomaly_component(
            row.get("max_sigma") or 0.0, bool(row.get("novel_type"))
        )
        e["raw"].update(
            max_delta_v_sigma=row.get("max_sigma"),
            novel_type=row.get("novel_type"),
            anomaly_count=row["event_count"],
        )

    items: list[ScoreItem] = []
    for object_id, e in objects.items():
        components = e["components"]
        # Debris-only objects below the standalone floor are population noise,
        # not per-object threats (else every tracked fragment makes the list).
        if (
            set(components) == {"debris"}
            and (e["raw"].get("debris_risk_score") or 0.0) < DEBRIS_STANDALONE_MIN
        ):
            continue
        composite = composite_score(components)
        if composite is None:
            continue
        items.append(
            ScoreItem(
                object_id=object_id,
                object_name=e["name"] or object_id,
                composite=composite,
                level=risk_level(composite),
                components=ScoreComponents(**components),
                raw=ScoreRaw(**e["raw"]),
            )
        )

    items.sort(key=lambda i: i.composite, reverse=True)
    return items


def _level_histogram(items: list[ScoreItem]) -> dict[str, int]:
    by_level: dict[str, int] = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for item in items:
        by_level[item.level] += 1
    return by_level


@router.get("/scores", response_model=ScoresResponse, summary="Composite threat scores")
async def get_scores(
    window_days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=1000, ge=1, le=5000),
    _subject: Subject = Depends(requires(DataDomain.MANEUVER_INTEL, Action.QUERY)),
) -> ScoresResponse:
    items = await _assemble_items(window_days)

    by_method: dict[str, int] = {k: 0 for k in WEIGHTS}
    for item in items:
        for method, value in item.components.model_dump().items():
            if value is not None:
                by_method[method] += 1

    return ScoresResponse(
        generated_at=datetime.now(UTC),
        window_days=window_days,
        weights=WEIGHTS,
        summary=ScoreSummary(
            total=len(items),
            by_level=_level_histogram(items),
            by_method=by_method,
        ),
        items=items[: max(1, min(int(limit), 5000))],
    )


@router.get(
    "/scores/history",
    response_model=ScoresHistoryResponse,
    summary="Threat-level histogram over the last N days",
)
async def get_scores_history(
    days: int = Query(default=14, ge=2, le=60),
    window_days: int = Query(default=30, ge=1, le=365),
    _subject: Subject = Depends(requires(DataDomain.MANEUVER_INTEL, Action.QUERY)),
) -> ScoresHistoryResponse:
    # Debris has no event history — fetch/enrich once, reuse for every anchor.
    debris_rows = [_enrich(r) for r in await query_debris(limit=20000)]
    today = datetime.now(UTC).date()
    points: list[ScoreHistoryPoint] = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        as_of = datetime.combine(day, time(23, 59, 59), tzinfo=UTC)
        items = await _assemble_items(window_days, as_of=as_of, debris_rows=debris_rows)
        points.append(ScoreHistoryPoint(date=day, by_level=_level_histogram(items)))
    return ScoresHistoryResponse(window_days=window_days, days=days, points=points)
