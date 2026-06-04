"""conjunction screening + CDM store (Stage 4)

Revision ID: 0002_conjunctions
Revises: 0001_canonical_catalog
Create Date: 2026-06-04

Adds the ``conjunction`` table that holds both CDM-sourced and engine-screened
close approaches (dev-plan §5 Stage 4 / roadmap O2). The severity enum is the
trust-calibrated tier surfaced to analysts; it is reused by the durable alert
log in a later migration. Authored as explicit DDL for the enum types, matching
migration 0001.

No foreign keys on the participant object ids: a CDM secondary is frequently an
uncatalogued/foreign object, and screening may reference rows ingested out of
order — coupling conjunction rows to catalog presence would drop valid events.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_conjunctions"
down_revision: str | None = "0001_canonical_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE conjunction_severity AS ENUM ('LOW', 'MOD', 'HIGH');")
    op.execute("CREATE TYPE conjunction_source AS ENUM ('CDM', 'SCREENING');")

    op.execute(
        """
        CREATE TABLE conjunction (
            id                      text PRIMARY KEY,
            source                  conjunction_source   NOT NULL,
            cdm_id                  text,
            primary_object_id       text                 NOT NULL,
            primary_norad_cat_id    integer,
            primary_name            text                 NOT NULL,
            secondary_object_id     text                 NOT NULL,
            secondary_norad_cat_id  integer,
            secondary_name          text                 NOT NULL,
            tca                     timestamptz          NOT NULL,
            miss_distance_km        double precision     NOT NULL,
            relative_speed_km_s     double precision,
            probability             double precision,
            severity                conjunction_severity NOT NULL,
            screened_at             timestamptz          NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX conjunction_tca_idx       ON conjunction (tca);")
    op.execute("CREATE INDEX conjunction_severity_idx  ON conjunction (severity);")
    op.execute("CREATE INDEX conjunction_primary_idx   ON conjunction (primary_object_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS conjunction;")
    op.execute("DROP TYPE IF EXISTS conjunction_source;")
    op.execute("DROP TYPE IF EXISTS conjunction_severity;")
