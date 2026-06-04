"""durable alert log (Stage 4)

Revision ID: 0003_alert_log
Revises: 0002_conjunctions
Create Date: 2026-06-04

The append-and-triage alert log behind the dashboard's alert center (dev-plan §5
Stage 4: "a durable alert log in Postgres" + acknowledge/triage). Conjunction
alerts carry a severity tier (reusing the ``conjunction_severity`` enum from
migration 0002) and a JSONB payload (the full conjunction) for drill-down.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_alert_log"
down_revision: str | None = "0002_conjunctions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE alert_status AS ENUM ('NEW', 'ACK', 'DISMISSED');")
    op.execute(
        """
        CREATE TABLE alert (
            id               text         PRIMARY KEY,
            type             text         NOT NULL,
            severity         conjunction_severity,
            object_id        text,
            conjunction_id   text,
            message          text         NOT NULL,
            payload          jsonb        NOT NULL DEFAULT '{}'::jsonb,
            status           alert_status NOT NULL DEFAULT 'NEW',
            acknowledged_by  text,
            acknowledged_at  timestamptz,
            created_at       timestamptz  NOT NULL DEFAULT now(),
            updated_at       timestamptz  NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX alert_status_idx     ON alert (status);")
    op.execute("CREATE INDEX alert_created_at_idx ON alert (created_at DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alert;")
    op.execute("DROP TYPE IF EXISTS alert_status;")
