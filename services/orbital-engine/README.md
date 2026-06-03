# Orbital Engine (`services/orbital-engine`)

Python 3.12 + FastAPI domain/compute tier for SpaceHawk. This is the authoritative
service for ingestion, the CCSDS/OMM canonical catalog, server-side SGP4/SDP4
propagation, conjunction screening, maneuver/RPO analytics, and (later) ML and LLM
serving.

> **Status:** placeholder created in Stage 0 (monorepo restructure). The FastAPI
> skeleton (health, OpenAPI, settings, structured logging) and the generated
> TypeScript client land in the Stage 0 backend sub-task.

The web tier reaches this service only over a private internal API; it never serves
HTML. See the repo root `README.md` for the overall monorepo layout.
