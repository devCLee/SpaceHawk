"""Audit query endpoint (Stage 5): ADMIN-only, read-only view of the log."""

from __future__ import annotations

from datetime import datetime
from typing import Any

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


@router.get("/audit", response_model=list[AuditEntry], summary="Query the audit log (ADMIN)")
async def get_audit(
    subject: str | None = Query(default=None, description="Filter by acting subject"),
    decision: str | None = Query(default=None, description="permit / deny"),
    limit: int = Query(default=100, ge=1, le=1000),
    _admin: Subject = Depends(requires(DataDomain.AUDIT, Action.READ)),
) -> list[dict[str, Any]]:
    return await query_audit(subject=subject, decision=decision, limit=limit)
