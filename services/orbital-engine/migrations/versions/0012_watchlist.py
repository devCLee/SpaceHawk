"""per-user watchlist + report_job owner (HWPX pipeline A1)

Revision ID: 0012_watchlist
Revises: 0011_report_job_images
Create Date: 2026-06-24

A user's 관심 목록 (watchlist) is persisted server-side, per user, so the daily
report's §1 관심목록 can count ONLY the generating user's watchlist instead of the
whole catalog. ``watchlist_item`` is the durable list: one row per (user, object),
keyed on the catalog ``object_id`` (the USOID the catalog/web use everywhere), with
a UNIQUE(username, object_id) so an add is idempotent.

The report job runs in a Celery worker with no request user, so the generating
user must be recorded on the job row: ``report_job.owner_username`` (nullable — a
job created without an owner, or an old row, simply gets the empty §1 message).
See ``orbital_engine.repository`` (watchlist fns) and
``orbital_engine.reports.assembler._watchlist``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012_watchlist"
down_revision: str | None = "0011_report_job_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE watchlist_item (
            id          bigserial   PRIMARY KEY,
            username    text        NOT NULL,
            object_id   text        NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT watchlist_item_username_object_id_key UNIQUE (username, object_id)
        );
        """
    )
    op.execute("CREATE INDEX watchlist_item_username_idx ON watchlist_item (username);")
    op.execute("ALTER TABLE report_job ADD COLUMN owner_username text;")


def downgrade() -> None:
    op.execute("ALTER TABLE report_job DROP COLUMN IF EXISTS owner_username;")
    op.execute("DROP TABLE IF EXISTS watchlist_item;")
