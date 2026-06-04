"""Audit subsystem: record every authorization decision, query the log.

``record_decision`` is called from the enforcement dependency for every permit
and deny. Writing is **best-effort**: a transient audit-store failure is logged
loudly (structured) but must not turn a 403 into a 500 or block enforcement —
availability of the control plane does not depend on the audit store being up.
The store itself is immutable (see migration 0005), so what is written cannot
later be altered. Reading the log is an ADMIN-only action (audited in turn).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Request
from sqlalchemy import text

from orbital_engine.db import get_engine
from orbital_engine.logging import get_logger
from orbital_engine.security.attributes import Action, DataDomain, Subject
from orbital_engine.security.policy import Decision

log = get_logger("orbital_engine.audit")

# Cap how long a decision waits on the audit store. Enforcement latency must not
# be hostage to a slow/unreachable audit DB: when healthy the write completes in
# well under this, and a deny is still served (best-effort) if it is not.
_AUDIT_WRITE_TIMEOUT_SEC = 2.0

_INSERT_SQL = text(
    """
    INSERT INTO audit_log
        (subject, role, service, source_ip, domain, action, decision, code, reason, method, path)
    VALUES
        (:subject, :role, :service, :source_ip, :domain, :action, :decision, :code, :reason, :method, :path)
    """
)


async def _write(entry: dict[str, Any]) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(_INSERT_SQL, entry)


async def record_decision(
    *,
    subject: Subject,
    request: Request,
    domain: DataDomain,
    action: Action,
    decision: Decision,
) -> None:
    """Persist one access decision (best-effort; never raises)."""
    entry = {
        "subject": subject.username,
        "role": subject.role.value,
        "service": subject.service.value,
        "source_ip": request.client.host if request.client else None,
        "domain": domain.value,
        "action": action.value,
        "decision": "permit" if decision.permit else "deny",
        "code": decision.code,
        "reason": decision.reason,
        "method": request.method,
        "path": request.url.path,
    }
    try:
        await asyncio.wait_for(_write(entry), timeout=_AUDIT_WRITE_TIMEOUT_SEC)
    except Exception as exc:  # noqa: BLE001 - audit must not break enforcement
        # Loud, structured: a dropped audit write is itself a security signal.
        log.error("audit.write_failed", error=str(exc), **entry)


async def query_audit(
    *,
    subject: str | None = None,
    decision: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return audit rows newest-first, optionally filtered by subject/decision."""
    clauses: list[str] = []
    params: dict[str, Any] = {"lim": max(1, min(int(limit), 1000))}
    if subject:
        clauses.append("subject = :subject")
        params["subject"] = subject
    if decision:
        clauses.append("decision = :decision")
        params["decision"] = decision
    where = f"WHERE {' AND '.join(clauses)} " if clauses else ""
    sql = text(
        "SELECT id, ts, subject, role, service, source_ip, domain, action, "
        f"decision, code, reason, method, path FROM audit_log {where}"
        "ORDER BY ts DESC, id DESC LIMIT :lim"
    )
    async with get_engine().connect() as conn:
        result = await conn.execute(sql, params)
        return [dict(row) for row in result.mappings()]
