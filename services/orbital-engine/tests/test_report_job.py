"""Async report-job orchestration: idempotency + pipeline run (HWPX R7).

The pure logic (idempotency key, create-or-return dedup, image persistence, and
the assemble→sanitize→prose→fill orchestration) is tested WITHOUT live infra:

* ``compute_idempotency_key`` — a plain function, tested directly.
* ``create_report_job`` — driven against a small in-memory fake connection that
  emulates the ``report_job`` unique-key semantics (INSERT … ON CONFLICT DO
  NOTHING + the image-refresh UPDATE + SELECT-by-key), so the dedup +
  enqueue-once + image-persistence contracts are covered with no Postgres.
* the success / stage-failure runs exercise ``_build_hwpx`` with an injected fake
  LLM client (no live provider, but the REAL ``write_report_prose`` guard runs)
  and the REAL bundled template (fillable since R6), proving DONE bytes pass
  ``validate_hwpx`` (with a web-supplied globe image embedded) and that a stage
  exception surfaces with no output.
* image (de)serialization round-trips ``ReportImages`` through the stored shape.

An infra-gated round-trip (real Postgres) covers ``create_report_job`` + ``_run``
end to end when infra is available; it is skipped otherwise, mirroring
``test_gp_history``.
"""

from __future__ import annotations

import io
import struct
import zlib
from datetime import UTC, date, datetime
from typing import Any

import pytest
from hwpx import HwpxDocument
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import dml
from sqlalchemy.sql.selectable import Select

from orbital_engine import db
from orbital_engine.reports import tasks
from orbital_engine.reports.models import (
    ReportJob,
    ReportStatus,
    deserialize_images,
    serialize_images,
)
from orbital_engine.reports.narrative import SectionError, write_report_prose
from orbital_engine.reports.schemas import (
    ConjunctionRow,
    CountryActivity,
    DailyReportPayload,
    DebrisRiskCounts,
    HighRiskDebrisRow,
    ReportImages,
    ReportProse,
    SatellitePass,
    WatchlistRow,
)
from orbital_engine.reports.validate import validate_hwpx

PK_SIGNATURE = b"PK"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# --------------------------------------------------------------------------- #
# tiny fixtures
# --------------------------------------------------------------------------- #


def _tiny_png() -> bytes:
    """A minimal but valid 1x1 PNG (no matplotlib dependency in tests)."""

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\xff\xff")
    return PNG_SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def _payload() -> DailyReportPayload:
    """A small but representative payload (every section non-empty)."""
    return DailyReportPayload(
        report_date=date(2026, 6, 22),
        watchlist_matrix=[
            WatchlistRow(country_code="US", country_name="미국", leo=10, meo=1, geo=2, heo=0, total=13),
        ],
        watchlist_total=WatchlistRow(
            country_code="TOTAL", country_name="합계", leo=10, meo=1, geo=2, heo=0, total=13
        ),
        country_activity=[
            CountryActivity(
                country_code="NK",
                country_name="북한",
                passes=[
                    SatellitePass(
                        satellite_name="KMS-4",
                        satellite_id="41332",
                        pass_time=datetime(2026, 6, 22, 3, 14, tzinfo=UTC),
                        closest_distance_km=412.5,
                        elevation_deg=42.0,
                    ),
                ],
            ),
        ],
        conjunctions=[
            ConjunctionRow(
                satellite_name="KOMPSAT-5",
                object_name="DEBRIS-9",
                tca=datetime(2026, 6, 22, 3, 14, tzinfo=UTC),
                distance_km=0.842,
                probability=1e-4,
                risk_category="HIGH",
            ),
        ],
        debris_risk_counts=DebrisRiskCounts(critical=1, high=2, moderate=3, low=4),
        debris_altitudes_km=[412.0, 800.0, 812.0, 824.0, 1420.0],
        high_risk_debris=[
            HighRiskDebrisRow(
                country_code="PRC",
                country_name="중국",
                debris_name="CZ-2C DEB",
                risk_grade="심각",
                rcs_size="LARGE",
                mean_altitude_km=812.0,
                period_min=101.0,
                perigee_km=800.0,
                apogee_km=824.0,
            ),
        ],
    )


def _images() -> ReportImages:
    """Web-supplied images: one globe snapshot (the NK section)."""
    return ReportImages(country_globes={"NK": _tiny_png()})


class _FakeLLMClient:
    """Stand-in OpenAI-compatible client: returns clean tokenized Korean prose.

    Tokenized + digit-free so the narrative no-numerals guard passes; the real
    ``write_report_prose`` runs unchanged over it (only the provider is faked).
    """

    def __init__(self) -> None:
        self.chat = self
        self.completions = self

    def create(self, *, model: str, messages: list[dict[str, str]]) -> Any:
        text = (
            '{"analysis_items": [{"detail": "여러 객체에 대한 정성적 분석 결과입니다.", '
            '"cause_forecast": "OBJ-A 관련 동향으로 인한 영향으로 분석됩니다."}], '
            '"response_ops": ["대응 작전을 지속 추진합니다."]}'
        )
        message = type("Msg", (), {"content": text})()
        choice = type("Choice", (), {"message": message})()
        return type("Resp", (), {"choices": [choice]})()


def _pipeline(**overrides: Any) -> tasks.ReportPipeline:
    """A pipeline wired to the fake LLM client over the REAL narrative path."""
    base: dict[str, Any] = {"prose_fn": write_report_prose, "llm_client": _FakeLLMClient()}
    base.update(overrides)
    return tasks.ReportPipeline(**base)


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
# image (de)serialization
# --------------------------------------------------------------------------- #


def test_serialize_images_roundtrip() -> None:
    png = _tiny_png()
    images = ReportImages(country_globes={"NK": png, "CN": png}, debris_density=png)
    stored = serialize_images(images)

    assert stored is not None
    assert isinstance(stored["country_globes"]["NK"], str)  # base64 ASCII, JSON-safe
    assert stored["debris_heatmap"] is None

    back = deserialize_images(stored)
    assert back.country_globes == {"NK": png, "CN": png}
    assert back.debris_density == png
    assert back.debris_heatmap is None


def test_serialize_images_empty_is_none_and_deserialize_none_is_empty() -> None:
    assert serialize_images(None) is None
    assert serialize_images(ReportImages()) is None  # nothing supplied → NULL column
    empty = deserialize_images(None)
    assert empty.country_globes == {} and empty.debris_density is None


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
    The image-refresh UPDATE (issued on a repeat create with new images) patches
    the stored row's ``input_images`` in place.
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
        if isinstance(statement, dml.Update):
            compiled = statement.compile(dialect=postgresql.dialect())
            key = compiled.params.get("idempotency_key_1")
            row = self.by_key.get(key)
            if row is not None:
                row["input_images"] = compiled.params.get("input_images")
            return _FakeResult([])
        if isinstance(statement, Select):
            key = statement.compile(dialect=postgresql.dialect()).params.get("idempotency_key_1")
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
# image persistence: create stores images; load rebuilds ReportImages
# --------------------------------------------------------------------------- #


async def test_create_report_job_persists_images() -> None:
    conn = _FakeConn()
    enqueued: list[str] = []
    images = _images()

    job = await tasks.create_report_job(
        "daily", date(2026, 6, 22), None, conn, images=images, enqueue=enqueued.append
    )

    # Stored as base64 JSONB on the row, and the loaded job carries that shape.
    assert job.input_images is not None
    assert isinstance(job.input_images["country_globes"]["NK"], str)
    # _run loads it back into a ReportImages identical to what the web supplied.
    loaded = deserialize_images(job.input_images)
    assert loaded.country_globes == images.country_globes


async def test_create_report_job_without_images_stores_null() -> None:
    conn = _FakeConn()
    job = await tasks.create_report_job(
        "daily", date(2026, 6, 22), None, conn, enqueue=lambda _jid: None
    )
    assert job.input_images is None
    assert deserialize_images(job.input_images).country_globes == {}


async def test_repeat_create_refreshes_images_only_when_supplied() -> None:
    conn = _FakeConn()
    enqueued: list[str] = []
    d = date(2026, 6, 22)

    # First create with no images → NULL stored, enqueued once.
    await tasks.create_report_job("daily", d, None, conn, enqueue=enqueued.append)
    # Repeat create WITH images → same job, no re-enqueue, but images refreshed.
    refreshed = await tasks.create_report_job(
        "daily", d, None, conn, images=_images(), enqueue=enqueued.append
    )

    assert len(conn.by_key) == 1
    assert len(enqueued) == 1  # never re-enqueued
    assert refreshed.input_images is not None
    assert "NK" in refreshed.input_images["country_globes"]


# --------------------------------------------------------------------------- #
# pipeline orchestration (no live LLM; REAL fillable template)
# --------------------------------------------------------------------------- #


def test_build_hwpx_success_embeds_image_and_passes_validation() -> None:
    pipeline = _pipeline()
    data = tasks._build_hwpx(_payload(), _images(), pipeline, pipeline.settings)

    assert data.startswith(PK_SIGNATURE)
    validate_hwpx(data)  # raises on any defect

    # Every image anchor is filled (Fix C): 4 country globes + §5b density +
    # heatmap. Anchors the web didn't supply get a generated fallback image, so
    # the count is the full 6 regardless of how many real images were provided.
    reopened = HwpxDocument.open(io.BytesIO(data))
    assert len(reopened.list_images()) == 6, "expected 4 globes + density + heatmap (real or fallback)"


def test_build_hwpx_renders_and_injects_density_chart() -> None:
    # density_chart_fn is invoked with the payload's altitudes, and its PNG output
    # is what reaches the filler as images.debris_density (engine-rendered).
    sentinel = _tiny_png()
    captured: dict[str, Any] = {}

    def _fake_density(altitudes: Any) -> bytes:
        captured["altitudes"] = list(altitudes)
        return sentinel

    embedded: dict[str, Any] = {}

    def _capture_fill(_payload: Any, _prose: Any, images: ReportImages) -> bytes:
        embedded["debris_density"] = images.debris_density
        embedded["country_globes"] = dict(images.country_globes)
        embedded["debris_heatmap"] = images.debris_heatmap
        return PK_SIGNATURE + b"stub"

    payload = _payload()
    pipeline = _pipeline(density_chart_fn=_fake_density, fill_fn=_capture_fill)
    tasks._build_hwpx(payload, _images(), pipeline, pipeline.settings)

    assert captured["altitudes"] == payload.debris_altitudes_km
    # Engine-rendered density reaches the filler; web globe is left untouched.
    assert embedded["debris_density"] == sentinel
    assert embedded["country_globes"] == _images().country_globes
    assert embedded["debris_heatmap"] is None


def test_engine_density_takes_precedence_over_web_supplied() -> None:
    # A web-supplied debris_density is OVERWRITTEN by the engine render.
    web_density = b"web-supplied-not-used"
    engine_png = _tiny_png()
    embedded: dict[str, Any] = {}

    def _capture_fill(_payload: Any, _prose: Any, images: ReportImages) -> bytes:
        embedded["debris_density"] = images.debris_density
        return PK_SIGNATURE + b"stub"

    images = ReportImages(country_globes={"NK": _tiny_png()}, debris_density=web_density)
    pipeline = _pipeline(density_chart_fn=lambda _a: engine_png, fill_fn=_capture_fill)
    tasks._build_hwpx(_payload(), images, pipeline, pipeline.settings)

    assert embedded["debris_density"] == engine_png  # engine wins, not web_density


def test_build_hwpx_stage_failure_propagates() -> None:
    def _boom(*_: Any, **__: Any) -> ReportProse:
        raise SectionError("provider exhausted")

    pipeline = tasks.ReportPipeline(prose_fn=_boom)
    with pytest.raises(SectionError):
        tasks._build_hwpx(_payload(), _images(), pipeline, pipeline.settings)


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
            "daily", date(2026, 6, 22), {"k": "v"}, conn, images=_images(), enqueue=enqueued.append
        )
        # second call inside the same tx: same key → returns the existing row, no enqueue.
        again = await tasks.create_report_job(
            "daily", date(2026, 6, 22), {"k": "v"}, conn, images=_images(), enqueue=enqueued.append
        )

    assert isinstance(job, ReportJob)
    assert again.id == job.id
    assert enqueued == [job.id]
    assert job.status is ReportStatus.PENDING
    # Images persisted on the row and reload into a ReportImages.
    assert deserialize_images(job.input_images).country_globes == _images().country_globes

    await _delete_job(job.id)
    await db.dispose()


async def test_run_pipeline_to_done(infra_up: bool) -> None:
    """End-to-end ``_run`` against real infra + REAL template: job → DONE, valid HWPX."""
    enqueued: list[str] = []
    async with db.get_engine().begin() as conn:
        job = await tasks.create_report_job(
            "daily", date(2026, 6, 22), None, conn, images=_images(), enqueue=enqueued.append
        )

    status = await tasks._run(job.id, pipeline=_pipeline())
    assert status is ReportStatus.DONE

    async with db.get_engine().connect() as conn:
        done = await tasks._load_job(conn, job.id)
    assert done is not None
    assert done.status is ReportStatus.DONE
    assert done.result is not None and done.result.startswith(PK_SIGNATURE)
    validate_hwpx(done.result)  # stored bytes pass the gate

    await _delete_job(job.id)
    await db.dispose()
