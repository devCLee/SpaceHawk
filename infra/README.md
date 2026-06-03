# Infrastructure (`infra/`)

Local-development and (eventually) air-gapped-enclave deployment assets for SpaceHawk:
Docker Compose, database/cache services, reverse proxy, and the offline supply-chain
strategy (vendored npm/PyPI mirrors, self-hosted Cesium assets, in-enclave model
registry).

> **Status:** placeholder created in Stage 0 (monorepo restructure). The
> `docker compose` stack (Postgres + PostGIS + TimescaleDB, Redis, both apps) and the
> Alembic migration scaffold land in the Stage 0 infra sub-task; the full offline
> deployment bundle is built out in later stages.

See the repo root `README.md` for the overall monorepo layout.
