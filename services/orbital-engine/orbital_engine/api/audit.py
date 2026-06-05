"""Audit query endpoint (Stage 5): ADMIN-only, read-only view of the log."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from orbital_engine.security.attributes import Action, DataDomain, Subject
from orbital_engine.security.audit import query_audit
from orbital_engine.security.enforce import requires

router = APIRouter(tags=["audit"])


class AuditEntry(BaseModel):
    id: int
    ts: datetime
    subject: str | None = None
    role: str | None = None
    service: str | None = None
    source_ip: str | None = None
    domain: str
    action: str
    decision: str
    code: str
    reason: str
    method: str | None = None
    path: str | None = None


class AuditPage(BaseModel):
    """One page of audit rows plus the total matching count (for page-count calc)."""

    rows: list[AuditEntry]
    total: int


@router.get("/audit", response_model=AuditPage, summary="Query the audit log (ADMIN)")
async def get_audit(
    subject: str | None = Query(default=None, description="Substring match on subject"),
    path: str | None = Query(default=None, description="Substring match on request path"),
    source_ip: str | None = Query(default=None, description="Substring match on source IP"),
    decision: Annotated[list[str] | None, Query(description="permit / deny (OR)")] = None,
    role: Annotated[list[str] | None, Query(description="Filter by role (OR)")] = None,
    domain: Annotated[list[str] | None, Query(description="Filter by data domain (OR)")] = None,
    action: Annotated[list[str] | None, Query(description="Filter by action (OR)")] = None,
    ts_from: Annotated[datetime | None, Query(description="Earliest ts (inclusive)")] = None,
    ts_to: Annotated[datetime | None, Query(description="Latest ts (inclusive)")] = None,
    limit: int = Query(default=100, ge=1, le=1000, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Rows to skip (page * size)"),
    _admin: Subject = Depends(requires(DataDomain.AUDIT, Action.READ)),
) -> dict[str, Any]:
    return await query_audit(
        subject=subject,
        path=path,
        source_ip=source_ip,
        decision=decision,
        role=role,
        domain=domain,
        action=action,
        ts_from=ts_from,
        ts_to=ts_to,
        limit=limit,
        offset=offset,
    )
