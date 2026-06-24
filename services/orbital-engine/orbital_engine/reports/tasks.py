"""Async daily-report job: idempotent create + Celery-driven pipeline run (T7).

This is the integration seam that wires the report modules
(:mod:`~orbital_engine.reports.assembler` → :mod:`~.sanitize` → :mod:`~.narrative`
→ :mod:`~.hwpx_filler` → :mod:`~.validate`) behind a persisted
:class:`~orbital_engine.reports.models.ReportJob` and a Celery task. Report
*images* (country globes + the two debris charts) are no longer rendered here —
they are SUPPLIED BY THE WEB at create time, persisted on the job row, and handed
to :func:`~orbital_engine.reports.hwpx_filler.fill_daily_report` during the run.

Async-in-Celery pattern (mirrored from ``orbital_engine.scheduler.tasks`` — the
ingest tasks are thin sync wrappers that drive an async runner via
``asyncio.run``): :func:`run_report_job` is the registered Celery task and is a
synchronous wrapper around the async :func:`_run`.

Idempotency: :func:`create_report_job` computes a stable key from the request and
INSERTs ``ON CONFLICT (idempotency_key) DO NOTHING``; if the row already existed
it is returned unchanged and NO task is enqueued, so a repeated request never
duplicates work even under a race (the unique index is the source of truth).

Injectable pipeline: every stage that needs the outside world (the LLM client,
and the prose/fill/validate callables) is supplied through :class:`ReportPipeline`
with production defaults, so tests can run the full orchestration with a fake LLM
client (driving the real narrative path) and the bundled — now fillable (R6) —
template.

Secrets: the LLM api key is never logged. Failures log only the stage/reason.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from orbital_engine.config import Settings, get_settings
from orbital_engine.db import get_engine
from orbital_engine.reports.assembler import assemble_daily
from orbital_engine.reports.charts import render_debris_density, render_debris_heatmap
from orbital_engine.reports.hwpx_filler import fill_daily_report
from orbital_engine.reports.models import (
    ReportJob,
    ReportStatus,
    deserialize_images,
    report_job,
    serialize_images,
)
from orbital_engine.reports.narrative import write_report_prose
from orbital_engine.reports.sanitize import to_llm_facts
from orbital_engine.reports.schemas import DailyReportPayload, ReportImages, ReportProse
from orbital_engine.reports.validate import validate_hwpx

logger = logging.getLogger(__name__)


class _Conn(Protocol):
    """The injected read/write connection: just what the job calls on it."""

    async def execute(self, statement: Any, parameters: Any = ...) -> Any: ...


# --------------------------------------------------------------------------- #
# idempotency
# --------------------------------------------------------------------------- #


def compute_idempotency_key(
    report_type: str,
    report_date: date,
    filters: Mapping[str, Any] | None,
) -> str:
    """Stable sha256 hex of the normalized request inputs.

    Normalization: report_type verbatim, the date as ISO-8601, and the filters as
    JSON with sorted keys (so key order never changes the hash). ``None`` filters
    and ``{}`` hash identically — both mean "no filters".
    """
    normalized = {
        "report_type": report_type,
        "report_date": report_date.isoformat(),
        "filters": dict(sorted((filters or {}).items())),
    }
    blob = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# injectable pipeline
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ReportPipeline:
    """The pipeline stages, each injectable for tests; defaults are production.

    ``prose_fn`` and ``fill_fn`` are the two seams tests override: ``prose_fn`` to
    avoid a live LLM (or forwarded a fake ``llm_client`` so the real narrative
    path runs over a faked provider), ``fill_fn`` to use a synthetic template if
    desired. ``fill_fn`` is called as ``fill_fn(payload, prose, images)`` — the
    web-supplied :class:`ReportImages` flow in from the persisted job row.
    """

    assemble_fn: Callable[..., Any] = assemble_daily
    sanitize_fn: Callable[[DailyReportPayload], Any] = to_llm_facts
    prose_fn: Callable[..., ReportProse] = write_report_prose
    fill_fn: Callable[..., bytes] = fill_daily_report
    validate_fn: Callable[[bytes], None] = validate_hwpx
    density_chart_fn: Callable[[Sequence[float]], bytes] = render_debris_density
    heatmap_chart_fn: Callable[[Sequence[Sequence[float]]], bytes] = render_debris_heatmap
    llm_client: Any | None = None
    settings: Settings = field(default_factory=get_settings)


# --------------------------------------------------------------------------- #
# create (idempotent) + enqueue
# --------------------------------------------------------------------------- #


async def _fetch_by_key(conn: _Conn, key: str) -> ReportJob | None:
    result = await conn.execute(
        select(report_job).where(report_job.c.idempotency_key == key)
    )
    row = result.mappings().first()
    return ReportJob.from_row(dict(row)) if row is not None else None


async def create_report_job(
    report_type: str,
    report_date: date,
    filters: Mapping[str, Any] | None,
    conn: _Conn,
    *,
    images: ReportImages | None = None,
    owner_username: str | None = None,
    enqueue: Callable[[str], Any] | None = None,
) -> ReportJob:
    """Idempotently create (or return) the job for this request, enqueuing once.

    Computes the idempotency key; INSERTs a PENDING row ``ON CONFLICT
    (idempotency_key) DO NOTHING``. If the insert created the row, the Celery task
    is enqueued (``run_report_job.delay(job_id)`` by default; overridable for
    tests). If the key already existed, the existing job is returned unchanged and
    nothing is enqueued — no duplicate row, no re-enqueue.

    Images: the web-supplied :class:`ReportImages` are persisted on the row (as
    base64 JSONB via :func:`~orbital_engine.reports.models.serialize_images`) so
    the image-less Celery task can rebuild them. Images are NOT part of the
    idempotency key (same date = same report); on a repeat create, the supplied
    images REFRESH the stored set so a later/better render wins. A create with no
    images stores NULL and does not clobber an existing set.

    Owner: ``owner_username`` (the requesting user, passed by the router) is stored
    on the row so the image-less Celery run knows whose 관심 목록 to filter §1 by —
    the worker has no request user. It is NOT part of the idempotency key (the same
    day's report is the same job regardless of who asked first); an existing row's
    owner is left as-is on a repeat create.

    ``conn`` is an injected async connection (caller-owned), mirroring
    ``assemble_daily``. The caller is responsible for the surrounding transaction.
    """
    key = compute_idempotency_key(report_type, report_date, filters)
    now = datetime.now(UTC)
    job_id = uuid.uuid4().hex
    stored_images = serialize_images(images)

    stmt = (
        pg_insert(report_job)
        .values(
            id=job_id,
            idempotency_key=key,
            report_type=report_type,
            report_date=report_date,
            filters_json=dict(filters) if filters else None,
            input_images=stored_images,
            owner_username=owner_username,
            status=ReportStatus.PENDING,
            error_reason=None,
            result=None,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(report_job.c.id)
    )
    result = await conn.execute(stmt)
    inserted_id = result.scalar_one_or_none()

    # Refresh images on a repeat create (only when new ones were supplied) so a
    # better/later web render replaces an earlier one; never clobber with NULL.
    if inserted_id is None and stored_images is not None:
        await conn.execute(
            update(report_job)
            .where(report_job.c.idempotency_key == key)
            .values(input_images=stored_images, updated_at=now)
        )

    job = await _fetch_by_key(conn, key)
    if job is None:  # pragma: no cover - INSERT or pre-existing row guarantees one
        raise RuntimeError(f"report_job vanished after upsert for key {key}")

    if inserted_id is not None:
        # We created the row → enqueue exactly once.
        dispatch = enqueue or (lambda jid: run_report_job.delay(jid))
        dispatch(job.id)

    return job


# --------------------------------------------------------------------------- #
# run (the async pipeline) + Celery task
# --------------------------------------------------------------------------- #


async def _set_status(
    conn: _Conn,
    job_id: str,
    status: ReportStatus,
    *,
    error_reason: str | None = None,
    result: bytes | None = None,
) -> None:
    """Advance a job's status (and optionally its error/result) with a fresh stamp."""
    values: dict[str, Any] = {"status": status, "updated_at": datetime.now(UTC)}
    if error_reason is not None:
        values["error_reason"] = error_reason
    if result is not None:
        values["result"] = result
    await conn.execute(update(report_job).where(report_job.c.id == job_id).values(**values))


async def _load_job(conn: _Conn, job_id: str) -> ReportJob | None:
    result = await conn.execute(select(report_job).where(report_job.c.id == job_id))
    row = result.mappings().first()
    return ReportJob.from_row(dict(row)) if row is not None else None


async def _run(job_id: str, *, pipeline: ReportPipeline | None = None) -> ReportStatus:
    """Execute the full pipeline for ``job_id``; returns the terminal status.

    Loads the job (including its persisted web-supplied images) and marks it
    RUNNING, then runs assemble → sanitize → prose → fill (with the loaded
    images) → validate. On success the validated HWPX is stored and the job is
    DONE. On ANY stage exception the job is FAILED with ``error_reason`` and NO
    partial output is stored (the failure UPDATE only touches status/error).
    """
    pipeline = pipeline or ReportPipeline()
    settings = pipeline.settings

    async with get_engine().begin() as conn:
        job = await _load_job(conn, job_id)
        if job is None:
            raise RuntimeError(f"report_job {job_id} not found")
        await _set_status(conn, job_id, ReportStatus.RUNNING)
        report_date = job.report_date
        owner_username = job.owner_username
        images = deserialize_images(job.input_images)

    try:
        async with get_engine().connect() as conn:
            payload = await pipeline.assemble_fn(
                report_date, conn, settings=settings, owner_username=owner_username
            )
        data = _build_hwpx(payload, images, pipeline, settings)
        pipeline.validate_fn(data)
    except Exception as exc:  # noqa: BLE001 - any stage failure is a job failure
        reason = f"{type(exc).__name__}: {exc}"
        logger.warning("report job %s failed: %s", job_id, reason)
        async with get_engine().begin() as conn:
            await _set_status(conn, job_id, ReportStatus.FAILED, error_reason=reason)
        return ReportStatus.FAILED

    async with get_engine().begin() as conn:
        await _set_status(conn, job_id, ReportStatus.DONE, result=data)
    logger.info("report job %s done (%d bytes)", job_id, len(data))
    return ReportStatus.DONE


def _build_hwpx(
    payload: DailyReportPayload,
    images: ReportImages,
    pipeline: ReportPipeline,
    settings: Settings,
) -> bytes:
    """Render §5b charts → sanitize → prose → fill, returning HWPX bytes.

    ``images`` is the web-supplied :class:`ReportImages` loaded off the job row.
    Both §5b charts are rendered ENGINE-SIDE and overwrite their image slots so they
    always appear regardless of the web UI: the 고도별 잔해 밀도 bar chart from the
    payload's scored debris altitudes (``debris_density``) and the 2D 잔해 밀도
    히트맵 from the payload's risk-weighted lon×lat grid (``debris_heatmap``). The
    engine render takes precedence over any web-supplied density/heatmap so both
    charts always match the engine's own ``debris_risk_counts``. The web-supplied
    ``country_globes`` are left untouched. The (possibly refreshed) images are handed
    to ``fill_fn(payload, prose, images)``; missing images are best-effort and never
    fail the fill.
    """
    images = images.model_copy(
        update={
            "debris_density": pipeline.density_chart_fn(payload.debris_altitudes_km),
            "debris_heatmap": pipeline.heatmap_chart_fn(payload.debris_heatmap_grid),
        }
    )
    sanitize_result = pipeline.sanitize_fn(payload)
    prose = pipeline.prose_fn(sanitize_result, client=pipeline.llm_client, settings=settings)
    return pipeline.fill_fn(payload, prose, images)


# Registered lazily so importing this module does not require a configured broker
# (mirrors the scheduler tasks living on the shared celery_app). The Celery task
# is a thin sync wrapper over the async runner, exactly like ingest_source.
try:  # pragma: no cover - exercised on a worker, not in unit tests
    from orbital_engine.scheduler.celery_app import celery_app

    @celery_app.task(name="orbital_engine.reports.tasks.run_report_job")
    def run_report_job(job_id: str) -> str:
        """Celery entry point: run the report pipeline for ``job_id`` synchronously."""
        return asyncio.run(_run(job_id)).value

except Exception:  # pragma: no cover - no broker configured (e.g. some unit envs)
    def run_report_job(job_id: str) -> str:  # type: ignore[misc]
        """Fallback when Celery is unavailable: run the pipeline inline."""
        return asyncio.run(_run(job_id)).value


__all__ = [
    "ReportPipeline",
    "compute_idempotency_key",
    "create_report_job",
    "run_report_job",
]
