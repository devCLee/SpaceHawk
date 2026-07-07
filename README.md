# SpaceHawk

<p align="center">
  <img src="https://i.ibb.co/C3sQgnnH/2026-07-04-153440.png" alt="SpaceHawk operational dashboard" width="900">
</p>

## SpaceHawk Space Environment & Threat Intelligence Operational Dashboard for Integrated Layered Operations

A Space Domain Awareness (SDA) & real-time operational dashboard, delivered as a
polyglot monorepo: a Next.js web/BFF tier and a Python "Orbital Engine" compute tier.

### Screenshots

<!-- Captions below are placeholders. I couldn't load the images to see which view each shows,
     so rename each one to match its content (e.g. "3D orbital view", "Conjunction screening",
     "Maneuver detection"). Source images are full-resolution PNGs hosted on ImgBB. -->

![SpaceHawk dashboard screenshot](https://i.ibb.co/Q7FqtJXz/2026-07-04-153108.png)
*SpaceHawk operational dashboard — view 2*

![SpaceHawk dashboard screenshot](https://i.ibb.co/DgsZt7BJ/2026-07-04-152116.png)
*SpaceHawk operational dashboard — view 3*

![SpaceHawk dashboard screenshot](https://i.ibb.co/5XKGvgFy/2026-07-04-151220.png)
*SpaceHawk operational dashboard — view 4*

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
