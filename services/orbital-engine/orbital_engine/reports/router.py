"""HTTP surface for the async daily-report (HWPX) pipeline (T8).

Three ANALYST-gated routes over the persisted :class:`~orbital_engine.reports.models.ReportJob`
(T7 owns creation/enqueue + the pipeline run; this router only creates and reads):

``POST /reports`` idempotently creates a job (via :func:`create_report_job`) and returns
202 with the job id + status. ``GET /reports/{job_id}`` returns the job status, adding a
``download_url`` once it is DONE. ``GET /reports/{job_id}/download`` streams the stored HWPX
bytes once the job is DONE (409 while still pending/running/failed).

All routes sit in the ``REPORTS`` data domain (P0-RBAC-ABAC §2), which the policy matrix
floors at ANALYST — so VIEWERs get a 403 and anonymous callers a 401, exactly like the
maneuver-intel surface. The handlers open their own async connection from the shared engine
(the repository convention here; there is no FastAPI DB Depends), write under ``begin()`` and
read under ``connect()``.
"""

from __future__ import annotations

import base64
import binascii
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from orbital_engine.db import get_engine
from orbital_engine.reports.models import ReportJob, ReportStatus, report_job
from orbital_engine.reports.schemas import ReportCountry, ReportImages
from orbital_engine.reports.tasks import create_report_job
from orbital_engine.security.attributes import Action, DataDomain, Subject
from orbital_engine.security.enforce import requires

router = APIRouter(prefix="/reports", tags=["reports"])

HWPX_MEDIA_TYPE = "application/vnd.hancom.hwpx"

# Per-image decoded-size ceiling. The web supplies PNG snapshots (a globe view,
# a debris chart, a heatmap); a few MB each is generous for those. A larger blob
# is rejected (413) rather than persisted, so a malformed/oversized upload can't
# bloat the job row.
MAX_IMAGE_BYTES = 4 * 1024 * 1024

# The country codes the report tracks (§2 북한, §3 중/러/일). Unknown keys in the
# request's country_globes map are ignored rather than rejected.
_REPORT_COUNTRY_CODES = frozenset(c.value for c in ReportCountry)


class ReportImagesRequest(BaseModel):
    """Optional web-supplied report images as base64-encoded PNGs.

    All fields optional so a no-image POST is valid. ``country_globes`` maps a
    report-country code (NK/CN/RU/JP) to a base64 PNG; unknown keys are dropped.
    """

    country_globes: dict[str, str] = Field(default_factory=dict)
    debris_density: str | None = None
    debris_heatmap: str | None = None


class CreateReportRequest(BaseModel):
    """Request body for a daily-report job."""

    report_type: str = "daily"
    report_date: date
    filters: dict[str, Any] | None = None
    images: ReportImagesRequest | None = None


def _decode_image(b64: str, *, field: str) -> bytes:
    """Decode one base64 PNG to bytes, enforcing validity + the size cap.

    Invalid base64 → 422; a decoded blob over :data:`MAX_IMAGE_BYTES` → 413. The
    field name is echoed so the client can tell which image was rejected.
    """
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid base64 for image '{field}'",
        ) from exc
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"image '{field}' exceeds {MAX_IMAGE_BYTES} bytes",
        )
    return raw


def _build_images(req: ReportImagesRequest | None) -> ReportImages | None:
    """Decode the request's base64 images into a :class:`ReportImages`, or None.

    Drops unknown country codes; returns ``None`` when nothing decodable remains
    so a no-image (or empty) request stores NULL and never clobbers a prior set.
    """
    if req is None:
        return None
    globes = {
        code: _decode_image(b64, field=f"country_globes.{code}")
        for code, b64 in req.country_globes.items()
        if code in _REPORT_COUNTRY_CODES
    }
    density = _decode_image(req.debris_density, field="debris_density") if req.debris_density else None
    heatmap = _decode_image(req.debris_heatmap, field="debris_heatmap") if req.debris_heatmap else None
    if not globes and density is None and heatmap is None:
        return None
    return ReportImages(country_globes=globes, debris_density=density, debris_heatmap=heatmap)


class CreateReportResponse(BaseModel):
    """The accepted job: id + current (PENDING) status."""

    job_id: str
    status: ReportStatus


class ReportStatusResponse(BaseModel):
    """A job's status; ``download_url`` is present only once DONE, ``error_reason`` only on FAILED."""

    job_id: str
    status: ReportStatus
    report_type: str
    report_date: date
    download_url: str | None = None
    error_reason: str | None = None
    filters: dict[str, Any] | None = Field(default=None)


async def _load_job(job_id: str) -> ReportJob | None:
    async with get_engine().connect() as conn:
        result = await conn.execute(select(report_job).where(report_job.c.id == job_id))
        row = result.mappings().first()
    return ReportJob.from_row(dict(row)) if row is not None else None


@router.post(
    "",
    response_model=CreateReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create (idempotently) a daily-report job",
)
async def create_report(
    body: CreateReportRequest,
    subject: Subject = Depends(requires(DataDomain.REPORTS, Action.QUERY)),
) -> CreateReportResponse:
    images = _build_images(body.images)
    async with get_engine().begin() as conn:
        job = await create_report_job(
            body.report_type,
            body.report_date,
            body.filters,
            conn,
            images=images,
            owner_username=subject.username,
        )
    return CreateReportResponse(job_id=job.id, status=job.status)


@router.get(
    "/{job_id}",
    response_model=ReportStatusResponse,
    summary="Report job status (+ download_url once DONE)",
)
async def get_report(
    job_id: str,
    _subject: Subject = Depends(requires(DataDomain.REPORTS, Action.READ)),
) -> ReportStatusResponse:
    job = await _load_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report job not found")
    download_url = f"{router.prefix}/{job.id}/download" if job.status is ReportStatus.DONE else None
    return ReportStatusResponse(
        job_id=job.id,
        status=job.status,
        report_type=job.report_type,
        report_date=job.report_date,
        download_url=download_url,
        error_reason=job.error_reason if job.status is ReportStatus.FAILED else None,
        filters=job.filters_json,
    )


@router.get(
    "/{job_id}/download",
    summary="Download the finished HWPX report",
    responses={200: {"content": {HWPX_MEDIA_TYPE: {}}}},
)
async def download_report(
    job_id: str,
    _subject: Subject = Depends(requires(DataDomain.REPORTS, Action.READ)),
) -> Response:
    job = await _load_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report job not found")
    if job.status is not ReportStatus.DONE or job.result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"report job is {job.status}, not DONE",
        )
    filename = f"{job.report_type}_report_{job.report_date.isoformat()}.hwpx"
    return Response(
        content=job.result,
        media_type=HWPX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
