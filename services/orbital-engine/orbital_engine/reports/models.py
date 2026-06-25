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

Input images (R7): the report's globe/debris images are rendered by the WEB and
supplied at job-create time (the Celery task only gets a ``job_id``), so they are
persisted on the row in the ``input_images`` JSONB column as base64-of-PNG (a
JSON-serializable, ``bytea``-free shape). :func:`serialize_images` /
:func:`deserialize_images` convert between the typed :class:`ReportImages` and
that stored form; ``None`` round-trips to an empty :class:`ReportImages`.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, Date, DateTime, LargeBinary, MetaData, String, Table
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB

from orbital_engine.reports.schemas import ReportImages

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
    Column("input_images", JSONB, nullable=True),
    # The user who generated the report (Celery runs with no request user, so the
    # owner is recorded on the row); §1 관심목록 is filtered to this user's watchlist.
    Column("owner_username", String, nullable=True),
    Column("status", _status_type, nullable=False),
    Column("error_reason", String, nullable=True),
    Column("result", LargeBinary, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


# --------------------------------------------------------------------------- #
# input-image (de)serialization: ReportImages <-> JSONB-of-base64
# --------------------------------------------------------------------------- #


def serialize_images(images: ReportImages | None) -> dict[str, Any] | None:
    """Pack a :class:`ReportImages` into the JSON-serializable stored shape.

    Bytes become base64 ASCII strings (JSONB cannot hold raw bytes). An empty /
    ``None`` ``images`` serializes to ``None`` so the column stays NULL when the
    web supplied nothing. Shape::

        {"country_globes": {"NK": "<b64>", ...},
         "debris_density": "<b64>"|null, "debris_heatmap": "<b64>"|null}
    """
    if images is None:
        return None
    globes = {code: base64.b64encode(png).decode("ascii") for code, png in images.country_globes.items()}
    density = base64.b64encode(images.debris_density).decode("ascii") if images.debris_density else None
    heatmap = base64.b64encode(images.debris_heatmap).decode("ascii") if images.debris_heatmap else None
    if not globes and density is None and heatmap is None:
        return None
    return {"country_globes": globes, "debris_density": density, "debris_heatmap": heatmap}


def deserialize_images(stored: dict[str, Any] | None) -> ReportImages:
    """Rebuild a :class:`ReportImages` from the stored base64 shape.

    ``None`` (column NULL) yields an empty :class:`ReportImages`, so a job created
    without images still runs the pipeline (images are optional). Inverse of
    :func:`serialize_images`.
    """
    if not stored:
        return ReportImages()
    globes = {
        code: base64.b64decode(b64) for code, b64 in (stored.get("country_globes") or {}).items()
    }
    density_b64 = stored.get("debris_density")
    heatmap_b64 = stored.get("debris_heatmap")
    return ReportImages(
        country_globes=globes,
        debris_density=base64.b64decode(density_b64) if density_b64 else None,
        debris_heatmap=base64.b64decode(heatmap_b64) if heatmap_b64 else None,
    )


@dataclass(slots=True)
class ReportJob:
    """A plain row projection of ``report_job`` (mirrors repository dict reads).

    Reads in the codebase return plain data, not ORM entities; this dataclass is
    that projection so callers/tests get attribute access without a session-bound
    instance. ``result`` carries the validated HWPX bytes once the job is DONE;
    ``input_images`` carries the stored (base64) web-supplied image shape, which
    :func:`deserialize_images` turns back into a :class:`ReportImages`.
    """

    id: str
    idempotency_key: str
    report_type: str
    report_date: date
    status: ReportStatus
    filters_json: dict[str, Any] | None = None
    input_images: dict[str, Any] | None = None
    owner_username: str | None = None
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
            input_images=row.get("input_images"),
            owner_username=row.get("owner_username"),
            error_reason=row.get("error_reason"),
            result=bytes(row["result"]) if row.get("result") is not None else None,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
