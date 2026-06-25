# SpaceHawk

## SpaceHawk Space Environment & Threat Intelligence Operational Dashboard for Integrated Layered Operations

A Space Domain Awareness (SDA) & real-time operational dashboard, delivered as a
polyglot monorepo: a Next.js web/BFF tier and a Python "Orbital Engine" compute tier.

### Monorepo layout

| Path | Tier | Stack | Status |
|---|---|---|---|
| `apps/web` | Web / BFF | Next.js 16 · React 19 · TypeScript · Cesium · satellite.js | Active (from the `lynx` base) |
| `services/orbital-engine` | Domain / compute | Python 3.12 · FastAPI | Scaffolded in Stage 0 |
| `packages/shared-types` | Shared contract | Generated TypeScript client from the FastAPI OpenAPI schema | Scaffolded in Stage 0 |
| `infra/` | Infra | Docker Compose · Postgres+PostGIS+TimescaleDB · Redis | Scaffolded in Stage 0 |

`apps/*` and `packages/*` are npm workspaces (single root lockfile). The Python
service is managed independently under `services/`.

### Common commands (run from the repo root)

| Command | Effect |
|---|---|
| `npm install` | Install all JS workspace dependencies |
| `npm run dev` | Run the web app (`apps/web`) in development |
| `npm run build` | Production build of the web app |
| `npm run lint` | Lint the web app |
| `npm run typecheck` | Type-check the web app |

Roadmap context and the staged delivery plan live alongside this repo's planning
documents; this monorepo implements **Stage 0 (Foundation, roadmap Phase 0)** first.
