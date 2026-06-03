# Infrastructure (`infra/`)

Local-development and (eventually) air-gapped-enclave deployment assets for SpaceHawk.

## Local stack

```bash
docker compose -f infra/docker-compose.yml up
```

Brings up four services:

| Service | Image / build | Port | Notes |
|---|---|---|---|
| `db` | `timescale/timescaledb-ha:pg16` | 5432 | PostgreSQL 16 + PostGIS + TimescaleDB |
| `redis` | `redis:7-alpine` | 6379 | hot state / pub-sub |
| `orbital-engine` | `infra/orbital-engine.Dockerfile` | 8000 | FastAPI; runs `alembic upgrade head` on start |
| `web` | `infra/web.Dockerfile` | 3000 | Next.js standalone |

Dev credentials default to `spacehawk` / `spacehawk` (see `.env.example`). Copy it
to `infra/.env` to override. These are **dev only**; the enclave supplies real
secrets out-of-band.

## Database migrations (Alembic)

The canonical catalog schema lives in `services/orbital-engine/migrations`
(reference DDL in `infra/db/ddl/`). Run from `services/orbital-engine` (venv active):

```bash
alembic upgrade head      # apply
alembic downgrade base    # roll back
```

The `orbital-engine` container applies migrations automatically on start for local
convenience; in the enclave, migrations run as a separate gated job.

## Still to come (later stages)

The full offline deployment bundle — vendored npm/PyPI mirrors, self-hosted Cesium
assets/imagery, in-enclave model registry, nginx reverse proxy, K8s manifests — is
built out in the deployment stage.
