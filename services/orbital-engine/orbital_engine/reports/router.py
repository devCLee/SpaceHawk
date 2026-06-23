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

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from orbital_engine.db import get_engine
from orbital_engine.reports.models import ReportJob, ReportStatus, report_job
from orbital_engine.reports.tasks import create_report_job
from orbital_engine.security.attributes import Action, DataDomain, Subject
from orbital_engine.security.enforce import requires

router = APIRouter(prefix="/reports", tags=["reports"])

HWPX_MEDIA_TYPE = "application/vnd.hancom.hwpx"


class CreateReportRequest(BaseModel):
    """Request body for a daily-report job."""

    report_type: str = "daily"
    report_date: date
    filters: dict[str, Any] | None = None


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
    _subject: Subject = Depends(requires(DataDomain.REPORTS, Action.QUERY)),
) -> CreateReportResponse:
    async with get_engine().begin() as conn:
        job = await create_report_job(body.report_type, body.report_date, body.filters, conn)
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
