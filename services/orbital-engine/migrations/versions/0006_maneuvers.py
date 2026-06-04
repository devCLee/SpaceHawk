"""maneuver detection store (Stage 6)

Revision ID: 0006_maneuvers
Revises: 0005_audit_log
Create Date: 2026-06-04

Adds the ``maneuver`` table holding detected element-set transitions flagged by
the V-pattern detector (dev-plan §5 Stage 6 / roadmap P2a feature #10). One row
per detected burn, keyed on a stable id (``MNV:<object>:<post-epoch>``) so a
re-scan over overlapping history upserts in place.

Mirrors ``gp_history``: a foreign key to ``space_object`` with ON DELETE CASCADE,
since a maneuver is only meaningful for a catalogued object whose history we hold.
Authored as explicit DDL, matching the surrounding migrations.

Δv / RIC decomposition and rule-based classification (feature #11) extend this
table in a later migration — this stage delivers the detection substrate only.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_maneuvers"
down_revision: str | None = "0005_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE maneuver (
            id                   text PRIMARY KEY,
            object_id            text        NOT NULL REFERENCES space_object (object_id) ON DELETE CASCADE,
            norad_cat_id         integer,
            object_name          text        NOT NULL,
            epoch_before         timestamptz NOT NULL,
            epoch_after          timestamptz NOT NULL,
            detected_epoch       timestamptz NOT NULL,
            delta_sma_km         double precision NOT NULL,
            delta_ecc            double precision NOT NULL,
            delta_inc_deg        double precision NOT NULL,
            delta_raan_deg       double precision NOT NULL,
            detection_statistic  double precision NOT NULL,
            confidence           double precision NOT NULL,
            detected_at          timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX maneuver_object_idx          ON maneuver (object_id);")
    op.execute("CREATE INDEX maneuver_detected_epoch_idx  ON maneuver (detected_epoch DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS maneuver;")
