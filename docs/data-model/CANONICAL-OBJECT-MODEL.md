# Canonical Space-Object Model

**Status:** Stage 0 (Foundation / roadmap P0) deliverable.
**Scope:** the single canonical object model the program standardizes on, per the
roadmap's "freeze a single CCSDS canonical model at the ARB" risk control.

SpaceHawk fuses several feeds (Space-Track, Celestrak, DISCOS, Leolabs). To avoid
tri-service data-model divergence, every record is normalized into one canonical
shape **before** it is stored, screened, propagated, analyzed, or displayed.

## 1. Basis: CCSDS OMM + Space-Track GP

The base already ships the target shape: `apps/web/src/data/main.json` is 268 objects
in **CCSDS OMM** form ("GENERATED VIA SPACE-TRACK.ORG API … ORIGINATOR: 18 SPCS"),
i.e. the Space-Track **GP** (General Perturbations) JSON — CCSDS OMM keywords plus
Space-Track catalog extensions (`OBJECT_TYPE`, `RCS_SIZE`, `COUNTRY_CODE`,
`LAUNCH_DATE`, `DECAY_DATE`, `SITE`, `GP_ID`, `FILE`, `TLE_LINE0/1/2`).

The canonical model **keeps these semantics** but:

- uses canonical `snake_case` field names (stable, language-neutral);
- replaces the all-string source payload with **proper types** (numbers, dates);
- adds a **Unified Space Object Identifier (USOID)** and **ingestion provenance**.

## 2. Three artifacts, one model

| Artifact | Path | Role |
|---|---|---|
| **JSON Schema** | `packages/shared-types/schemas/space-object.schema.json` | The language-neutral **source-of-truth contract** (Draft 2020-12). |
| **Pydantic models** | `services/orbital-engine/orbital_engine/domain/space_object.py` | Python implementation; ingests raw GP, coerces types, derives USOID. |
| **SQL DDL draft** | `infra/db/ddl/0001_canonical_catalog.sql` | Reference relational schema (Postgres + PostGIS + TimescaleDB). |

A Stage 0 test (`services/orbital-engine/tests/test_space_object.py`) parses the
sample catalog through the Pydantic model and asserts the serialized output validates
against the JSON Schema — so the three artifacts cannot silently drift.

## 3. Unified Space Object Identifier (USOID)

A stable internal primary key, deterministic across sources and ingestion cycles,
so the same physical object resolves to one record regardless of which feed supplied
it. Format `SH:<class>:<value>`, resolved most-stable-first:

| Precedence | Condition | USOID | Example |
|---|---|---|---|
| 1 | NORAD catalog number present | `SH:CAT:<9-digit zero-padded>` | `SH:CAT:000002778` |
| 2 | else International Designator present | `SH:INTL:<COSPAR id>` | `SH:INTL:1967-034D` |
| 3 | else source-scoped native id | `SH:SRC:<source>:<id>` | `SH:SRC:LEOLABS:L335` |

The NORAD field is widened to **9 digits** to accommodate the extended/9-digit
catalog (beyond the legacy 5-digit / Alpha-5 range). `norad_cat_id` and
`intl_designator` are retained as cross-reference identifiers alongside the USOID.

## 4. Field mapping (raw GP key → canonical field)

| CCSDS / Space-Track GP key | Canonical field | Type | Notes |
|---|---|---|---|
| `NORAD_CAT_ID` | `norad_cat_id` | int? | drives USOID precedence 1 |
| `OBJECT_ID` | `intl_designator` | str | COSPAR; USOID precedence 2 |
| `GP_ID` | `gp_id` | int? | provenance |
| `FILE` | `source_file_id` | int? | provenance |
| — | `data_source` | enum | `SPACE-TRACK`/`CELESTRAK`/`DISCOS`/`LEOLABS` |
| `ORIGINATOR` | `originator` | str? | e.g. `18 SPCS` |
| `CCSDS_OMM_VERS` | `ccsds_omm_vers` | str? | e.g. `3.0` |
| `COMMENT` | `comment` | str? | |
| `CREATION_DATE` | `creation_date` | datetime? | source message time |
| — | `ingested_at` | datetime? | set at ingestion |
| `OBJECT_NAME` | `object_name` | str | |
| `OBJECT_TYPE` | `object_type` | enum | PAYLOAD/ROCKET BODY/DEBRIS/UNKNOWN/TBA |
| `RCS_SIZE` | `rcs_size` | enum? | SMALL/MEDIUM/LARGE |
| `CLASSIFICATION_TYPE` | `classification_type` | enum | U/C/S |
| `COUNTRY_CODE` | `country_code` | str? | |
| `LAUNCH_DATE` | `launch_date` | date? | |
| `DECAY_DATE` | `decay_date` | date? | null ⇒ on-orbit |
| `SITE` | `site` | str? | |
| `CENTER_NAME` | `center_name` | str | default `EARTH` |
| `REF_FRAME` | `ref_frame` | str | `TEME` |
| `TIME_SYSTEM` | `time_system` | str | `UTC` |
| `MEAN_ELEMENT_THEORY` | `mean_element_theory` | enum | SGP4/SDP4 |
| `EPOCH` | `epoch` | datetime | mean-element epoch |
| `MEAN_MOTION` | `mean_motion` | float | rev/day |
| `ECCENTRICITY` | `eccentricity` | float | 0 ≤ e < 1 |
| `INCLINATION` | `inclination` | float | deg |
| `RA_OF_ASC_NODE` | `ra_of_asc_node` | float | deg |
| `ARG_OF_PERICENTER` | `arg_of_pericenter` | float | deg |
| `MEAN_ANOMALY` | `mean_anomaly` | float | deg |
| `EPHEMERIS_TYPE` | `ephemeris_type` | int | 0 for distributed TLEs |
| `ELEMENT_SET_NO` | `element_set_no` | int? | |
| `REV_AT_EPOCH` | `rev_at_epoch` | int? | |
| `BSTAR` | `bstar` | float? | 1/earth-radii |
| `MEAN_MOTION_DOT` | `mean_motion_dot` | float? | rev/day² |
| `MEAN_MOTION_DDOT` | `mean_motion_ddot` | float? | rev/day³ |
| `SEMIMAJOR_AXIS` | `semimajor_axis_km` | float? | derived |
| `PERIOD` | `period_min` | float? | derived |
| `APOAPSIS` | `apoapsis_km` | float? | derived |
| `PERIAPSIS` | `periapsis_km` | float? | derived |
| `TLE_LINE0/1/2` | `tle_line0/1/2` | str? | raw TLE |

Empty-string source values are normalized to `null`/`None` on ingestion.

## 5. Storage model (see DDL draft)

- **`space_object`** — current catalog, one row per `object_id` (USOID PK), holding
  the latest element set and object metadata; PostGIS-ready for footprint/geometry.
- **`gp_history`** — TimescaleDB hypertable, one row per `(object_id, epoch)`; the
  substrate for maneuver/RPO history and behavioral baselines (roadmap P2a).

## 6. Change control

This model is **frozen at the ARB**. Changes require a new section here, a JSON
Schema revision, matching Pydantic/DDL updates, and the drift test must stay green.

Post-freeze changes are recorded as numbered amendments in §7 and must be ratified
by the ARB (not merged silently) — the model is a tri-service contract.

## 7. Amendments

### A1 — DISCOS physical characteristics (enrichment source)

**Date:** 2026-06-05 · **Type:** additive, backward-compatible · **Status:** pending ARB ratification.

Adds physical-characteristic fields supplied by **ESA DISCOSweb** (dev-plan §3
feature #4, multi-source redundancy). DISCOS carries **no orbital state** (no epoch,
no mean elements), so it is **not** an element source: it cannot create a canonical
record (the Keplerian fields are `NOT NULL`). It is wired as a **metadata
enrichment pass** — fetched on a slow cadence and patched onto existing rows,
matched on NORAD (`satno`) or, failing that, COSPAR (`cosparId`). See
`services/orbital-engine/orbital_engine/ingestion/discos.py` and
`repository.apply_enrichments`.

**New fields** (all nullable; not in JSON Schema `required[]`):

| DISCOSweb attribute | Canonical field | Type | Notes |
|---|---|---|---|
| `objectClass` | `object_class` | str? | DISCOS object class (free text), e.g. `Payload`, `Rocket Body` |
| `mass` | `mass_kg` | float? | kilograms |
| `shape` | `shape` | str? | shape descriptor, e.g. `Box`, `Cyl`, `Sphere + 2 Pan` |
| max(`width`,`height`,`depth`,`diameter`,`length`,`span`) | `span_m` | float? | largest linear dimension, metres |
| `xSectMin` | `cross_section_min_m2` | float? | minimum cross-section, m² |
| `xSectAvg` | `cross_section_avg_m2` | float? | average cross-section, m² |
| `xSectMax` | `cross_section_max_m2` | float? | maximum cross-section, m² |

`satno`/`cosparId` are the join keys (the existing `norad_cat_id`/`intl_designator`
identity fields), not new fields.

**Why low-risk:** additive only — no existing field, type, or the `NOT NULL` element
contract changed; old records still validate (new fields default `null`). The
enrichment columns are **excluded from the element upsert set** in the repository,
so a re-ingest from Space-Track/Celestrak never overwrites DISCOS data with `null`.

**Artifacts updated** (the three-artifacts lockstep, §2):

- **JSON Schema** — 7 properties added to `space-object.schema.json`.
- **Pydantic** — fields added to `domain/space_object.py`.
- **DDL** — Alembic migration `0009_discos_physical` adds the columns to
  `space_object` (nullable, with non-negative `CHECK`s) + an `object_class` index.
- **Drift test** — `test_space_object.py` stays green (schema ↔ model in lockstep).
