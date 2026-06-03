"""canonical catalog: space_object + gp_history hypertable

Revision ID: 0001_canonical_catalog
Revises:
Create Date: 2026-06-03

Implements the canonical CCSDS/OMM catalog from
infra/db/ddl/0001_canonical_catalog.sql and the canonical model in
orbital_engine.domain.space_object. Authored as explicit DDL because it relies on
PostgreSQL extensions, enum types, and a TimescaleDB hypertable that are not
expressible through declarative ORM metadata.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_canonical_catalog"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")

    op.execute("CREATE TYPE data_source AS ENUM ('SPACE-TRACK', 'CELESTRAK', 'DISCOS', 'LEOLABS');")
    op.execute("CREATE TYPE object_type AS ENUM ('PAYLOAD', 'ROCKET BODY', 'DEBRIS', 'UNKNOWN', 'TBA');")
    op.execute("CREATE TYPE rcs_size AS ENUM ('SMALL', 'MEDIUM', 'LARGE');")
    op.execute("CREATE TYPE classification_type AS ENUM ('U', 'C', 'S');")
    op.execute("CREATE TYPE mean_element_theory AS ENUM ('SGP4', 'SDP4');")

    op.execute(
        """
        CREATE TABLE space_object (
            object_id            text PRIMARY KEY,
            norad_cat_id         integer UNIQUE,
            intl_designator      text        NOT NULL,
            gp_id                bigint,
            source_file_id       bigint,
            data_source          data_source NOT NULL DEFAULT 'SPACE-TRACK',
            originator           text,
            ccsds_omm_vers       text,
            comment              text,
            creation_date        timestamptz,
            ingested_at          timestamptz NOT NULL DEFAULT now(),
            object_name          text        NOT NULL,
            object_type          object_type NOT NULL,
            rcs_size             rcs_size,
            classification_type  classification_type NOT NULL DEFAULT 'U',
            country_code         text,
            launch_date          date,
            decay_date           date,
            site                 text,
            center_name          text        NOT NULL DEFAULT 'EARTH',
            ref_frame            text        NOT NULL DEFAULT 'TEME',
            time_system          text        NOT NULL DEFAULT 'UTC',
            mean_element_theory  mean_element_theory NOT NULL DEFAULT 'SGP4',
            epoch                timestamptz NOT NULL,
            mean_motion          double precision NOT NULL CHECK (mean_motion > 0),
            eccentricity         double precision NOT NULL CHECK (eccentricity >= 0 AND eccentricity < 1),
            inclination          double precision NOT NULL CHECK (inclination >= 0 AND inclination <= 180),
            ra_of_asc_node       double precision NOT NULL,
            arg_of_pericenter    double precision NOT NULL,
            mean_anomaly         double precision NOT NULL,
            ephemeris_type       integer     NOT NULL DEFAULT 0,
            element_set_no       integer,
            rev_at_epoch         integer,
            bstar                double precision,
            mean_motion_dot      double precision,
            mean_motion_ddot     double precision,
            semimajor_axis_km    double precision,
            period_min           double precision,
            apoapsis_km          double precision,
            periapsis_km         double precision,
            tle_line0            text,
            tle_line1            text,
            tle_line2            text
        );
        """
    )
    op.execute("CREATE INDEX space_object_object_type_idx  ON space_object (object_type);")
    op.execute("CREATE INDEX space_object_country_code_idx ON space_object (country_code);")
    op.execute("CREATE INDEX space_object_epoch_idx        ON space_object (epoch DESC);")
    op.execute(
        "CREATE INDEX space_object_decay_null_idx ON space_object (object_id) WHERE decay_date IS NULL;"
    )

    op.execute(
        """
        CREATE TABLE gp_history (
            object_id            text        NOT NULL REFERENCES space_object (object_id) ON DELETE CASCADE,
            epoch                timestamptz NOT NULL,
            data_source          data_source NOT NULL,
            gp_id                bigint,
            mean_motion          double precision NOT NULL,
            eccentricity         double precision NOT NULL,
            inclination          double precision NOT NULL,
            ra_of_asc_node       double precision NOT NULL,
            arg_of_pericenter    double precision NOT NULL,
            mean_anomaly         double precision NOT NULL,
            bstar                double precision,
            semimajor_axis_km    double precision,
            period_min           double precision,
            apoapsis_km          double precision,
            periapsis_km         double precision,
            tle_line1            text,
            tle_line2            text,
            ingested_at          timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (object_id, epoch)
        );
        """
    )
    op.execute("SELECT create_hypertable('gp_history', by_range('epoch'), if_not_exists => TRUE);")
    op.execute("CREATE INDEX gp_history_object_epoch_idx ON gp_history (object_id, epoch DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gp_history;")
    op.execute("DROP TABLE IF EXISTS space_object;")
    for enum in ("mean_element_theory", "classification_type", "rcs_size", "object_type", "data_source"):
        op.execute(f"DROP TYPE IF EXISTS {enum};")
