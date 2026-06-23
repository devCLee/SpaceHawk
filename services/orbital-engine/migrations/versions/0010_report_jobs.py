"""daily-report job records (HWPX pipeline T7)

Revision ID: 0010_report_jobs
Revises: 0009_discos_physical
Create Date: 2026-06-22

The persisted job record behind the async HWPX daily-report pipeline (dev-plan
report pipeline T7). One row per requested report: created PENDING when a report
is enqueued, advanced to RUNNING by the Celery worker, and ended DONE (with the
validated HWPX stored in ``result``) or FAILED (with ``error_reason``).

Idempotency: ``idempotency_key`` is a stable sha256 hex of the normalized request
(report_type + report_date isoformat + sorted filters). It is UNIQUE so a repeat
request returns the existing job instead of enqueuing a duplicate (the dedup is
enforced at the DB so a race cannot create two jobs for the same key).

The validated HWPX is stored inline as ``bytea`` (LargeBinary): the rest of the
engine persists everything in Postgres (the catalog, alerts, audit log) and has
no file-store abstraction, and ``validate.validate_hwpx`` hands the caller bytes,
so an inline column avoids inventing a filesystem/path lifecycle for the enclave.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_report_jobs"
down_revision: str | None = "0009_discos_physical"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE report_job_status AS ENUM ('PENDING', 'RUNNING', 'DONE', 'FAILED');")
    op.execute(
        """
        CREATE TABLE report_job (
            id               text              PRIMARY KEY,
            idempotency_key  text              NOT NULL,
            report_type      text              NOT NULL,
            report_date      date              NOT NULL,
            filters_json     jsonb,
            status           report_job_status NOT NULL DEFAULT 'PENDING',
            error_reason     text,
            result           bytea,
            created_at       timestamptz       NOT NULL DEFAULT now(),
            updated_at       timestamptz       NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE UNIQUE INDEX report_job_idempotency_key_idx ON report_job (idempotency_key);")
    op.execute("CREATE INDEX report_job_created_at_idx ON report_job (created_at DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS report_job;")
    op.execute("DROP TYPE IF EXISTS report_job_status;")
