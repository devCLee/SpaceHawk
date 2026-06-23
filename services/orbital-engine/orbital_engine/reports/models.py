"""Persistence model for the async daily-report job (HWPX pipeline T7).

The engine manages its schema with Alembic and talks to it via SQLAlchemy Core
(see :mod:`orbital_engine.db` / :mod:`orbital_engine.repository`), not declarative
ORM. Mirroring that, this module declares the ``report_job`` table as a Core
:class:`~sqlalchemy.Table` against a standalone :class:`~sqlalchemy.MetaData` (the
table itself is created by migration ``0010_report_jobs``; the ``Table`` here is
only the typed handle used to build INSERT/SELECT/UPDATE statements).

Result storage: the validated HWPX is kept inline as ``LargeBinary`` (Postgres
``bytea``). The engine persists everything else in Postgres and exposes no
file-store, and ``validate.validate_hwpx`` yields bytes — so an inline column is
the simplest correct option and avoids a filesystem/path lifecycle in the enclave.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, Date, DateTime, LargeBinary, MetaData, String, Table
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB

# Standalone metadata: this is a code-side handle for query building only. The
# authoritative DDL (table + unique index + enum type) lives in migration 0010.
metadata = MetaData()


class ReportStatus(StrEnum):
    """Lifecycle of a report job (matches the ``report_job_status`` enum in 0010)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


# ``name`` must equal the Postgres enum type created in the migration, and
# ``create_type=False`` keeps SQLAlchemy from trying to (re)emit it — Alembic owns it.
_status_type = SAEnum(
    ReportStatus,
    name="report_job_status",
    values_callable=lambda enum: [member.value for member in enum],
    create_type=False,
)

report_job = Table(
    "report_job",
    metadata,
    Column("id", String, primary_key=True),
    Column("idempotency_key", String, nullable=False, unique=True, index=True),
    Column("report_type", String, nullable=False),
    Column("report_date", Date, nullable=False),
    Column("filters_json", JSONB, nullable=True),
    Column("status", _status_type, nullable=False),
    Column("error_reason", String, nullable=True),
    Column("result", LargeBinary, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


@dataclass(slots=True)
class ReportJob:
    """A plain row projection of ``report_job`` (mirrors repository dict reads).

    Reads in the codebase return plain data, not ORM entities; this dataclass is
    that projection so callers/tests get attribute access without a session-bound
    instance. ``result`` carries the validated HWPX bytes once the job is DONE.
    """

    id: str
    idempotency_key: str
    report_type: str
    report_date: date
    status: ReportStatus
    filters_json: dict[str, Any] | None = None
    error_reason: str | None = None
    result: bytes | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ReportJob:
        """Build a :class:`ReportJob` from a mappings() row dict."""
        return cls(
            id=row["id"],
            idempotency_key=row["idempotency_key"],
            report_type=row["report_type"],
            report_date=row["report_date"],
            status=ReportStatus(row["status"]),
            filters_json=row.get("filters_json"),
            error_reason=row.get("error_reason"),
            result=bytes(row["result"]) if row.get("result") is not None else None,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
