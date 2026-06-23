"""Report-pipeline HTTP surface (T8): ABAC gate + create/status/download.

Auth deny paths (401/403) short-circuit before any DB/Celery work, so they run
without infra (mirrors ``test_authz``). The permit paths stub the two seams the
router calls — ``create_report_job`` (which owns the Celery enqueue) and the
job-loading read — so the route logic is exercised with no Postgres and no broker
(mirrors ``test_maneuvers_api`` monkeypatching the repository functions).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from orbital_engine.config import get_settings
from orbital_engine.main import create_app
from orbital_engine.reports import router as reports_api
from orbital_engine.reports.models import ReportJob, ReportStatus
from orbital_engine.security.tokens import mint_token

client = TestClient(create_app())


def _token(role: str, *, username: str = "operator1") -> str:
    settings = get_settings()
    claims = {
        "sub": username,
        "role": role,
        "service": "JOINT",
        "clr": "S",
        "scope": [],
        "grants": [],
    }
    return mint_token(claims, secret=settings.auth_jwt_secret, ttl_sec=300)


def _auth(role: str, **kw: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(role, **kw)}"}


def _job(status: ReportStatus, *, result: bytes | None = None, error: str | None = None) -> ReportJob:
    return ReportJob(
        id="rpt-123",
        idempotency_key="key-abc",
        report_type="daily",
        report_date=date(2026, 6, 1),
        status=status,
        filters_json=None,
        error_reason=error,
        result=result,
        created_at=datetime(2026, 6, 1),
        updated_at=datetime(2026, 6, 1),
    )


# --- Default-deny: no session ----------------------------------------------
def test_create_report_requires_auth() -> None:
    resp = client.post("/reports", json={"report_date": "2026-06-01"})
    assert resp.status_code == 401


def test_status_requires_auth() -> None:
    assert client.get("/reports/rpt-123").status_code == 401


def test_download_requires_auth() -> None:
    assert client.get("/reports/rpt-123/download").status_code == 401


# --- Forbidden: authenticated but below ANALYST (no DB reached) --------------
def test_viewer_cannot_create_report() -> None:
    resp = client.post("/reports", json={"report_date": "2026-06-01"}, headers=_auth("VIEWER"))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden: insufficient_role"


def test_viewer_cannot_read_status() -> None:
    resp = client.get("/reports/rpt-123", headers=_auth("VIEWER"))
    assert resp.status_code == 403


# --- Permit paths (seams stubbed; no infra, no broker) ----------------------
def test_analyst_creates_report(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_create(report_type, report_date, filters, conn, **kw):  # noqa: ANN001
        captured.update(report_type=report_type, report_date=report_date, filters=filters)
        return _job(ReportStatus.PENDING)

    monkeypatch.setattr(reports_api, "create_report_job", fake_create)
    resp = client.post(
        "/reports",
        json={"report_type": "daily", "report_date": "2026-06-01"},
        headers=_auth("ANALYST"),
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body == {"job_id": "rpt-123", "status": "PENDING"}
    assert captured["report_type"] == "daily"
    assert captured["report_date"] == date(2026, 6, 1)


def test_status_pending_has_no_download_url(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load(job_id):  # noqa: ANN001
        return _job(ReportStatus.PENDING)

    monkeypatch.setattr(reports_api, "_load_job", fake_load)
    resp = client.get("/reports/rpt-123", headers=_auth("ANALYST"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PENDING"
    assert body["download_url"] is None


def test_status_done_includes_download_url(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load(job_id):  # noqa: ANN001
        return _job(ReportStatus.DONE, result=b"PK\x03\x04hwpx")

    monkeypatch.setattr(reports_api, "_load_job", fake_load)
    resp = client.get("/reports/rpt-123", headers=_auth("ANALYST"))
    assert resp.status_code == 200
    assert resp.json()["download_url"] == "/reports/rpt-123/download"


def test_status_failed_includes_error_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load(job_id):  # noqa: ANN001
        return _job(ReportStatus.FAILED, error="FillError: boom")

    monkeypatch.setattr(reports_api, "_load_job", fake_load)
    resp = client.get("/reports/rpt-123", headers=_auth("ANALYST"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "FAILED"
    assert body["error_reason"] == "FillError: boom"
    assert body["download_url"] is None


def test_status_unknown_id_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load(job_id):  # noqa: ANN001
        return None

    monkeypatch.setattr(reports_api, "_load_job", fake_load)
    resp = client.get("/reports/nope", headers=_auth("ANALYST"))
    assert resp.status_code == 404


def test_download_not_ready_409(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load(job_id):  # noqa: ANN001
        return _job(ReportStatus.RUNNING)

    monkeypatch.setattr(reports_api, "_load_job", fake_load)
    resp = client.get("/reports/rpt-123/download", headers=_auth("ANALYST"))
    assert resp.status_code == 409


def test_download_unknown_id_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load(job_id):  # noqa: ANN001
        return None

    monkeypatch.setattr(reports_api, "_load_job", fake_load)
    resp = client.get("/reports/nope/download", headers=_auth("ANALYST"))
    assert resp.status_code == 404


def test_download_ready_streams_hwpx(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load(job_id):  # noqa: ANN001
        return _job(ReportStatus.DONE, result=b"PK\x03\x04hwpx-bytes")

    monkeypatch.setattr(reports_api, "_load_job", fake_load)
    resp = client.get("/reports/rpt-123/download", headers=_auth("ANALYST"))
    assert resp.status_code == 200
    assert resp.content == b"PK\x03\x04hwpx-bytes"
    assert resp.headers["content-type"] == "application/vnd.hancom.hwpx"
    assert resp.headers["content-disposition"] == 'attachment; filename="daily_report_2026-06-01.hwpx"'


def test_report_paths_in_openapi() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/reports" in paths
    assert "/reports/{job_id}" in paths
    assert "/reports/{job_id}/download" in paths
