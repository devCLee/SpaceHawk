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
from datetime import datetime
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


_SELECT_COLS = (
    "id, ts, subject, role, service, source_ip, domain, action, "
    "decision, code, reason, method, path"
)


def _build_where(
    text_filters: dict[str, str | None],
    list_filters: dict[str, list[str] | None],
    ts_from: datetime | None = None,
    ts_to: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    """Compose the shared WHERE clause + bound params for page and count queries.

    Text filters match by case-insensitive substring (``ILIKE '%term%'``); list
    filters match by inclusive OR (``col IN (...)``); ``ts_from``/``ts_to`` bound
    the timestamp to an inclusive range. All are parameterised — no user value is
    ever interpolated into SQL. Empty/blank inputs are ignored so an unset filter
    never narrows the result set.
    """
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for col, term in text_filters.items():
        if term and term.strip():
            clauses.append(f"{col} ILIKE :{col}")
            params[col] = f"%{term.strip()}%"
    for col, values in list_filters.items():
        chosen = [v for v in (values or []) if v]
        if chosen:
            keys = [f"{col}_{i}" for i in range(len(chosen))]
            params.update(dict(zip(keys, chosen, strict=True)))
            placeholders = ", ".join(f":{k}" for k in keys)
            clauses.append(f"{col} IN ({placeholders})")
    if ts_from is not None:
        clauses.append("ts >= :ts_from")
        params["ts_from"] = ts_from
    if ts_to is not None:
        clauses.append("ts <= :ts_to")
        params["ts_to"] = ts_to
    where = f"WHERE {' AND '.join(clauses)} " if clauses else ""
    return where, params


async def query_audit(
    *,
    subject: str | None = None,
    path: str | None = None,
    source_ip: str | None = None,
    decision: list[str] | None = None,
    role: list[str] | None = None,
    domain: list[str] | None = None,
    action: list[str] | None = None,
    ts_from: datetime | None = None,
    ts_to: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Return a page of audit rows (newest-first) plus the total matching count.

    Filtering is server-side: ``subject``/``path``/``source_ip`` are substring
    matches, ``decision``/``role``/``domain``/``action`` are multi-select OR
    filters, and ``ts_from``/``ts_to`` bound the timestamp range. The same WHERE
    clause drives both the page query and the COUNT, so ``total`` reflects the
    active filters (the UI uses it to compute the page count).
    """
    where, filter_params = _build_where(
        {"subject": subject, "path": path, "source_ip": source_ip},
        {"decision": decision, "role": role, "domain": domain, "action": action},
        ts_from=ts_from,
        ts_to=ts_to,
    )
    page_params = {
        **filter_params,
        "lim": max(1, min(int(limit), 1000)),
        "off": max(0, int(offset)),
    }
    rows_sql = text(
        f"SELECT {_SELECT_COLS} FROM audit_log {where}"
        "ORDER BY ts DESC, id DESC LIMIT :lim OFFSET :off"
    )
    count_sql = text(f"SELECT COUNT(*) FROM audit_log {where}")
    async with get_engine().connect() as conn:
        rows = [dict(row) for row in (await conn.execute(rows_sql, page_params)).mappings()]
        total = (await conn.execute(count_sql, filter_params)).scalar_one()
    return {"rows": rows, "total": int(total)}
