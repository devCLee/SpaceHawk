## Design and tooling decisions

This document records intentional choices so they are not “fixed” accidentally.

---

### Framework and language

- **Decision**: Use Next.js (App Router) with TypeScript and React.
- **Rationale**: Provides a modern, type‑safe React framework with good support for server‑side rendering and routing.
- **Implications**:
  - New pages and layouts should follow Next.js App Router conventions under `src/app`.
  - Prefer TypeScript types/interfaces over untyped JavaScript.

---

### Cesium integration

- **Decision**: Integrate Cesium via dedicated React components under `src/app/Components`.
- **Rationale**: Keeps 3D/map concerns isolated from general UI, and centralizes Cesium setup/teardown logic.
- **Implications**:
  - Cesium viewer setup and teardown should stay within these components or closely related modules.
  - Do not scatter direct Cesium API usage across unrelated pages; instead, extend the existing Cesium components.

---

### Cesium asset handling

- **Decision**: Copy Cesium build assets into `public/cesium` using the `copy-cesium` script.
- **Rationale**: Ensures Cesium’s static assets are available to the app without custom bundler integration.
- **Implications**:
  - Build and dev workflows rely on this copy step.
  - Changes to how assets are copied or served must preserve this availability or update all dependent code and docs accordingly.

---

### Validation commands

- **Decision**: Use `npm run lint` and `npm run build` as standard validation.
- **Rationale**: Aligns with Next.js defaults and provides quick feedback on code quality and build readiness.
- **Implications**:
  - All feature work should run these commands before completion.
  - Additional tests or checks, if introduced, should be documented here and in `docs/WORKFLOW.md`.

---

### Dependency management

- **Decision**: Keep dependencies minimal and prefer built‑in or existing solutions.
- **Rationale**: Reduces bundle size, complexity, and maintenance overhead.
- **Implications**:
  - Avoid adding new libraries when the same goal can be achieved with current stack.
  - Any new dependency must be justified and recorded here with its purpose.

---

### Ingestion scheduler (Stage 2)

- **Decision**: Use **Celery with a Redis broker** for periodic multi-source ingestion, rather than an in-process scheduler (e.g. APScheduler).
- **Rationale**: Stage 7 (P2b) ML jobs need a distributed task queue; reusing one broker now avoids re-platforming the scheduler later. Redis is already deployed for hot state, so the broker adds no new infrastructure type.
- **Implications**:
  - Ingestion runs as separate `worker` + `beat` processes (see `infra/docker-compose.yml`), not inside the FastAPI process.
  - Task logic stays in `orbital_engine.ingestion.runner` (async, unit-tested); Celery tasks in `orbital_engine.scheduler.tasks` are thin `asyncio.run` wrappers.
  - Per-source cadence lives in `beat_schedule`; unavailable sources are skipped inside the task, so activation is config-driven.

---

### Online globe imagery picker — curated to Ion-owned basemaps

- **Decision**: The online globe's `BaseLayerPicker` is curated to ONLY the
  imagery/terrain this Ion token owns and that loads through hosts already in the
  strict CSP (Ion `assets.ion.cesium.com`, Bing `*.virtualearth.net`, same-origin).
  Imagery: Bing Aerial / Aerial+Labels / Roads; Google Satellite / +Labels /
  Roadmap / Contour (Ion-proxied); Natural Earth II. Terrain: Cesium World Terrain,
  WGS84 Ellipsoid. The offline globe keeps the picker disabled.
- **Rationale**: Operators get a basemap selector with no broken options and no
  security regression. An earlier version enabled Cesium's full default grid and
  widened the CSP for ArcGIS/OSM/Stadia CDNs; that was **reverted** because those
  third parties are CSP-blocked (Stadia also needs a key) and several Ion defaults
  (Sentinel-2, Blue Marble, Earth at Night, Azure) 404 on this token. Filtering to
  owned Ion/Bing assets keeps real variety (two satellite sources + road/contour)
  without third-party egress.
- **Implications**:
  - CSP `connect-src`/`img-src` stay locked to Ion/Bing/`self` — Stage 5 intact, no
    third-party egress (enclave-safe). The earlier `baseLayerPickerImagerySrc`
    widening is removed.
  - The picker is built by filtering `createDefaultImageryProviderViewModels()` /
    `createDefaultTerrainProviderViewModels()` by name in `CesiumComponent.tsx`; if
    Cesium renames a default view model, the filter simply drops it (fail-safe — no
    broken/unowned option ever appears).
  - Adding a non-Ion provider (street maps, hillshade, artistic styles) would
    re-introduce the egress and requires re-widening the CSP + re-flagging it in
    `docs/design/STAGE-5-SECURITY-MEMO.md`.

---

### How to add new decisions

When you make a new intentional choice that will affect future work:

1. Add a new section with:
   - **Decision**
   - **Rationale**
   - **Implications**
2. Keep entries concise and focused on long‑term behavior and constraints.

