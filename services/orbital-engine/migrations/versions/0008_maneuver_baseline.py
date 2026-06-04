"""per-object behavioral baseline (Stage 6 fingerprinting)

Revision ID: 0008_maneuver_baseline
Revises: 0007_maneuver_classification
Create Date: 2026-06-04

Adds the ``maneuver_baseline`` table: one row per object summarizing how it
normally maneuvers (cadence + Δv robust statistics + purpose-class mix), the
substrate for the deviation/anomaly flagging in the innovation spine (dev-plan
§5 Stage 6 feature #14 / roadmap O4). Keyed on ``object_id`` (one current
baseline per object); rebuilt in place as new maneuvers accrue. FK to
``space_object`` ON DELETE CASCADE, matching ``gp_history`` / ``maneuver``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_maneuver_baseline"
down_revision: str | None = "0007_maneuver_classification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE maneuver_baseline (
            object_id           text PRIMARY KEY REFERENCES space_object (object_id) ON DELETE CASCADE,
            object_name         text             NOT NULL,
            sample_count        integer          NOT NULL,
            mean_interval_days  double precision,
            interval_mad_days   double precision,
            mean_delta_v_m_s    double precision NOT NULL,
            delta_v_mad_m_s     double precision NOT NULL,
            type_distribution   jsonb            NOT NULL DEFAULT '{}'::jsonb,
            last_epoch          timestamptz      NOT NULL,
            updated_at          timestamptz      NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX maneuver_baseline_last_epoch_idx ON maneuver_baseline (last_epoch DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS maneuver_baseline;")
