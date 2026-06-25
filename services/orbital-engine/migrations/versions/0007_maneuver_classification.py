"""maneuver Δv / RIC + rule-based classification (Stage 6)

Revision ID: 0007_maneuver_classification
Revises: 0006_maneuvers
Create Date: 2026-06-04

Extends the ``maneuver`` table (migration 0006) with the Δv / RIC decomposition
and the rule-based purpose class (dev-plan §5 Stage 6 feature #11). The new
numeric columns are nullable (rows detected before this migration carry no
estimate); ``maneuver_type`` defaults to ``UNKNOWN`` so existing rows get a valid,
honest label rather than a guessed one. Authored as explicit DDL, matching 0006.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_maneuver_classification"
down_revision: str | None = "0006_maneuvers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE maneuver_type AS ENUM "
        "('STATION_KEEPING', 'ORBIT_RAISE', 'ORBIT_LOWER', 'PHASING', 'RPO', 'UNKNOWN');"
    )
    op.execute(
        """
        ALTER TABLE maneuver
            ADD COLUMN sma_before_km        double precision,
            ADD COLUMN inclination_deg      double precision,
            ADD COLUMN delta_v_m_s          double precision,
            ADD COLUMN ric_radial_m_s       double precision,
            ADD COLUMN ric_in_track_m_s     double precision,
            ADD COLUMN ric_cross_track_m_s  double precision,
            ADD COLUMN maneuver_type        maneuver_type NOT NULL DEFAULT 'UNKNOWN';
        """
    )
    op.execute("CREATE INDEX maneuver_type_idx ON maneuver (maneuver_type);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS maneuver_type_idx;")
    op.execute(
        """
        ALTER TABLE maneuver
            DROP COLUMN IF EXISTS sma_before_km,
            DROP COLUMN IF EXISTS inclination_deg,
            DROP COLUMN IF EXISTS delta_v_m_s,
            DROP COLUMN IF EXISTS ric_radial_m_s,
            DROP COLUMN IF EXISTS ric_in_track_m_s,
            DROP COLUMN IF EXISTS ric_cross_track_m_s,
            DROP COLUMN IF EXISTS maneuver_type;
        """
    )
    op.execute("DROP TYPE IF EXISTS maneuver_type;")
