-- SpaceHawk canonical catalog — DDL DRAFT (Stage 0 design artifact).
--
-- This is the reference schema for the unified CCSDS/OMM catalog plus the
-- time-series element-set history. It mirrors the canonical model in
-- packages/shared-types/schemas/space-object.schema.json and
-- services/orbital-engine/orbital_engine/domain/space_object.py.
--
-- It is intentionally a hand-authored draft. The authoritative, versioned schema
-- is produced by the Alembic migrations stood up in the Stage 0 infra sub-task;
-- this file documents intent and is the starting point for migration 0001.

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;       -- co-planar / RPO geometry, footprints
CREATE EXTENSION IF NOT EXISTS timescaledb;   -- orbit & maneuver time-series history

-- ---------------------------------------------------------------------------
-- Enumerated types (kept in sync with the canonical model enums)
-- ---------------------------------------------------------------------------
CREATE TYPE data_source AS ENUM ('SPACE-TRACK', 'CELESTRAK', 'DISCOS', 'LEOLABS');
CREATE TYPE object_type AS ENUM ('PAYLOAD', 'ROCKET BODY', 'DEBRIS', 'UNKNOWN', 'TBA');
CREATE TYPE rcs_size AS ENUM ('SMALL', 'MEDIUM', 'LARGE');
CREATE TYPE classification_type AS ENUM ('U', 'C', 'S');
CREATE TYPE mean_element_theory AS ENUM ('SGP4', 'SDP4');

-- ---------------------------------------------------------------------------
-- space_object — current catalog (one row per object, latest element set)
-- ---------------------------------------------------------------------------
CREATE TABLE space_object (
    object_id            text PRIMARY KEY,           -- USOID, e.g. 'SH:CAT:000002778'
    norad_cat_id         integer UNIQUE,             -- nullable for uncatalogued objects
    intl_designator      text        NOT NULL,       -- COSPAR / OBJECT_ID
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

CREATE INDEX space_object_object_type_idx  ON space_object (object_type);
CREATE INDEX space_object_country_code_idx ON space_object (country_code);
CREATE INDEX space_object_epoch_idx        ON space_object (epoch DESC);
CREATE INDEX space_object_decay_null_idx   ON space_object (object_id) WHERE decay_date IS NULL; -- on-orbit

COMMENT ON TABLE space_object IS 'Unified CCSDS/OMM catalog; one row per object (latest element set). USOID primary key.';

-- ---------------------------------------------------------------------------
-- gp_history — time-series of element sets (TimescaleDB hypertable)
-- One row per (object, epoch); the substrate for maneuver/RPO history (P2a).
-- ---------------------------------------------------------------------------
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

-- Promote to a hypertable partitioned on epoch (run after table creation).
SELECT create_hypertable('gp_history', by_range('epoch'), if_not_exists => TRUE);

CREATE INDEX gp_history_object_epoch_idx ON gp_history (object_id, epoch DESC);

COMMENT ON TABLE gp_history IS 'Time-series of element sets per object (TimescaleDB hypertable); basis for maneuver/RPO history analytics.';
