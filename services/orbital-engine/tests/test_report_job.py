"""Async report-job orchestration: idempotency + pipeline run (HWPX T7).

The pure logic (idempotency key, create-or-return dedup, and the assemble→…→fill
orchestration) is tested WITHOUT live infra:

* ``compute_idempotency_key`` — a plain function, tested directly.
* ``create_report_job`` — driven against a small in-memory fake connection that
  emulates the ``report_job`` unique-key semantics (INSERT … ON CONFLICT DO
  NOTHING + SELECT-by-key), so the dedup + enqueue-once contract is covered with
  no Postgres.
* the success / stage-failure runs exercise ``_build_hwpx`` with an injected fake
  LLM client (no live provider) and a fillable SYNTHETIC template (the bundled
  one intentionally raises ``FillError``), proving DONE bytes pass ``validate_hwpx``
  and that a stage exception surfaces as a failure with a reason and no output.

An infra-gated round-trip (real Postgres) covers ``create_report_job`` end to end
when infra is available; it is skipped otherwise, mirroring ``test_gp_history``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

import pytest
from hwpx import HwpxDocument
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import dml
from sqlalchemy.sql.selectable import Select

from orbital_engine import db
from orbital_engine.reports import tasks
from orbital_engine.reports.hwpx_filler import SLOTMAP, fill_daily_report
from orbital_engine.reports.models import ReportJob, ReportStatus
from orbital_engine.reports.narrative import SectionError
from orbital_engine.reports.schemas import (
    ConjunctionRow,
    CountryBreakdownEntry,
    DailyReportPayload,
    SurveillanceCategoryCount,
)
from orbital_engine.reports.validate import validate_hwpx

PK_SIGNATURE = b"PK"


# --------------------------------------------------------------------------- #
# idempotency key
# --------------------------------------------------------------------------- #


def test_idempotency_key_is_stable_and_order_independent() -> None:
    d = date(2026, 6, 22)
    a = tasks.compute_idempotency_key("daily", d, {"country": "US", "regime": "LEO"})
    b = tasks.compute_idempotency_key("daily", d, {"regime": "LEO", "country": "US"})
    assert a == b  # filter key order must not change the hash
    assert len(a) == 64  # sha256 hex


def test_idempotency_key_distinguishes_inputs() -> None:
    d = date(2026, 6, 22)
    base = tasks.compute_idempotency_key("daily", d, None)
    assert base != tasks.compute_idempotency_key("weekly", d, None)
    assert base != tasks.compute_idempotency_key("daily", date(2026, 6, 23), None)
    assert base != tasks.compute_idempotency_key("daily", d, {"country": "US"})
    # None and {} both mean "no filters".
    assert base == tasks.compute_idempotency_key("daily", d, {})


# --------------------------------------------------------------------------- #
# in-memory fake connection emulating the report_job unique-key semantics
# --------------------------------------------------------------------------- #


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]], scalar: Any = None) -> None:
        self._rows = rows
        self._scalar = scalar

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def mappings(self) -> _FakeResult:
        return self

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakeConn:
    """Emulates exactly the statements ``create_report_job`` issues.

    Backed by a dict keyed on ``idempotency_key`` so a second INSERT with a
    duplicate key is a no-op (returns no inserted id) and the SELECT returns the
    first-written row — the real ON CONFLICT DO NOTHING + unique-index behavior.
    """

    def __init__(self) -> None:
        self.by_key: dict[str, dict[str, Any]] = {}

    async def execute(self, statement: Any, parameters: Any = None) -> _FakeResult:
        if isinstance(statement, dml.Insert):
            params = statement.compile(dialect=postgresql.dialect()).params
            key = params["idempotency_key"]
            if key in self.by_key:
                return _FakeResult([], scalar=None)  # conflict → DO NOTHING
            self.by_key[key] = dict(params)
            return _FakeResult([], scalar=params["id"])
        if isinstance(statement, Select):
            key = statement.compile(dialect=postgresql.dialect()).params.get(
                "idempotency_key_1"
            )
            row = self.by_key.get(key)
            return _FakeResult([row] if row else [])
        raise AssertionError(f"unexpected statement: {type(statement)}")


async def test_create_report_job_is_idempotent() -> None:
    conn = _FakeConn()
    enqueued: list[str] = []

    job1 = await tasks.create_report_job(
        "daily", date(2026, 6, 22), {"country": "US"}, conn, enqueue=enqueued.append
    )
    job2 = await tasks.create_report_job(
        "daily", date(2026, 6, 22), {"country": "US"}, conn, enqueue=enqueued.append
    )

    assert job1.id == job2.id  # same job returned
    assert len(conn.by_key) == 1  # one row
    assert enqueued == [job1.id]  # enqueued exactly once
    assert job1.status is ReportStatus.PENDING


async def test_create_report_job_distinct_inputs_create_distinct_jobs() -> None:
    conn = _FakeConn()
    enqueued: list[str] = []

    a = await tasks.create_report_job("daily", date(2026, 6, 22), None, conn, enqueue=enqueued.append)
    b = await tasks.create_report_job("daily", date(2026, 6, 23), None, conn, enqueue=enqueued.append)

    assert a.id != b.id
    assert len(conn.by_key) == 2
    assert enqueued == [a.id, b.id]


# --------------------------------------------------------------------------- #
# pipeline orchestration (no live LLM, no un-fillable bundled template)
# --------------------------------------------------------------------------- #


def _payload() -> DailyReportPayload:
    return DailyReportPayload(
        report_date=date(2026, 6, 22),
        surveillance_categories=[
            SurveillanceCategoryCount(category="위성(탑재체)", count=7),
        ],
        conjunctions=[
            ConjunctionRow(
                conjunction_id="CDM-1",
                primary_object_id="OBJ-A",
                primary_name="KOMPSAT-5",
                secondary_object_id="OBJ-B",
                secondary_name="DEBRIS-9",
                miss_distance_km=0.842,
                probability=1e-4,
                tca=datetime(2026, 6, 22, 3, 14, tzinfo=UTC),
                alert_level="HIGH",
            ),
        ],
        country_breakdown=[
            CountryBreakdownEntry(owner_code="US", owner_name="미국", count=120),
        ],
    )


def _synthetic_template_bytes() -> bytes:
    """A fillable template carrying every SLOTMAP anchor (mirrors test_hwpx_filler)."""
    doc = HwpxDocument.new()
    for label in ["보고일자", "감시위성 합계", "최우선 근접 위성", "최우선 근접 거리", "최다 보유국"]:
        table = doc.add_table(1, 2)
        table.set_cell_text(0, 0, label, logical=True)
    for label in ["개요 본문", "분석내용 본문", "향후추진 본문"]:
        table = doc.add_table(2, 1)
        table.set_cell_text(0, 0, label, logical=True)
    for slot in SLOTMAP.charts:
        table = doc.add_table(2, 1)
        table.set_cell_text(0, 0, slot.label, logical=True)
    return doc.to_bytes()


class _FakeLLMClient:
    """Stand-in OpenAI-compatible client: returns clean tokenized Korean prose.

    Tokenized + digit-free so the narrative no-numerals guard passes; the real
    ``write_report_prose`` runs unchanged over it (only the provider is faked).
    """

    def __init__(self) -> None:
        self.chat = self
        self.completions = self

    def create(self, *, model: str, messages: list[dict[str, str]]) -> Any:
        text = "여러 객체에 대한 정성적 분석 결과입니다. OBJ-A 관련 동향을 서술합니다."
        message = type("Msg", (), {"content": text})()
        choice = type("Choice", (), {"message": message})()
        return type("Resp", (), {"choices": [choice]})()


def _fillable_fill(template_bytes: bytes):
    def _fill(payload: Any, prose: Mapping[str, str], charts: Mapping[str, bytes], **_: Any) -> bytes:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".hwpx", delete=False) as fh:
            fh.write(template_bytes)
            path = fh.name
        return fill_daily_report(payload, prose, charts, template_path=path)

    return _fill


def test_build_hwpx_success_passes_validation() -> None:
    pipeline = tasks.ReportPipeline(
        prose_fn=tasks.write_report_prose,
        fill_fn=_fillable_fill(_synthetic_template_bytes()),
        llm_client=_FakeLLMClient(),
    )
    # write_report_prose needs sleep=no-op? it defaults to time.sleep but never
    # sleeps on success (no retries), so the fake client returns immediately.
    data = tasks._build_hwpx(_payload(), pipeline, pipeline.settings)

    assert data.startswith(PK_SIGNATURE)
    validate_hwpx(data)  # raises on any defect


def test_build_hwpx_stage_failure_propagates() -> None:
    def _boom(*_: Any, **__: Any) -> dict[str, str]:
        raise SectionError("provider exhausted")

    pipeline = tasks.ReportPipeline(
        prose_fn=_boom,
        fill_fn=_fillable_fill(_synthetic_template_bytes()),
    )
    with pytest.raises(SectionError):
        tasks._build_hwpx(_payload(), pipeline, pipeline.settings)


# --------------------------------------------------------------------------- #
# infra-gated end-to-end: real create_report_job + _run round-trip
# --------------------------------------------------------------------------- #


@pytest.fixture
async def infra_up() -> bool:
    if not await db.ping():
        pytest.skip("Postgres not available — skipping report_job round-trip")
    return True


async def _delete_job(job_id: str) -> None:
    from sqlalchemy import text as _text

    async with db.get_engine().begin() as conn:
        await conn.execute(_text("DELETE FROM report_job WHERE id = :id"), {"id": job_id})


async def test_create_report_job_roundtrip(infra_up: bool) -> None:
    enqueued: list[str] = []
    async with db.get_engine().begin() as conn:
        job = await tasks.create_report_job(
            "daily", date(2026, 6, 22), {"k": "v"}, conn, enqueue=enqueued.append
        )
        # second call inside the same tx: same key → returns the existing row, no enqueue.
        again = await tasks.create_report_job(
            "daily", date(2026, 6, 22), {"k": "v"}, conn, enqueue=enqueued.append
        )

    assert isinstance(job, ReportJob)
    assert again.id == job.id
    assert enqueued == [job.id]
    assert job.status is ReportStatus.PENDING

    await _delete_job(job.id)
    await db.dispose()
