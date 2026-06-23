"""persist web-supplied report input images (HWPX pipeline R7)

Revision ID: 0011_report_job_images
Revises: 0010_report_jobs
Create Date: 2026-06-24

The daily-report globe/debris images are rendered by the WEB and handed in at
job-create time, but the Celery worker only receives a ``job_id`` — so the images
must live on the job row to survive the hand-off. This adds a nullable
``input_images`` JSONB column holding base64-of-PNG (a JSON-serializable shape,
no ``bytea``): ``{country_globes: {NK: <b64>, ...}, debris_density: <b64>|null,
debris_heatmap: <b64>|null}``. NULL means "no images supplied" (the pipeline runs
with blank image anchors). See ``orbital_engine.reports.models.serialize_images``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011_report_job_images"
down_revision: str | None = "0010_report_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE report_job ADD COLUMN input_images jsonb;")


def downgrade() -> None:
    op.execute("ALTER TABLE report_job DROP COLUMN IF EXISTS input_images;")
