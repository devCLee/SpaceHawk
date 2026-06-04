# Stage 3 — Frontend: scalable visualization, search & pass tools

*(Dev-plan Stage 3 → roadmap P1 "visualization"; M5–M7. Features #1–#3, #9a–#9i.)*

## Objective

Turn the lynx Cesium shell into an operational dashboard that renders the full
catalog at ≥10k objects and gives analysts the catalog-interaction and
object-inspection toolset, consuming the Stage-2 Orbital-Engine API.

## Starting point (verified on `develop`)

- Stages 0–2 merged. Engine API live: `GET /catalog` (q / object_type /
  country_code / limit / offset), `GET /catalog/{id}` (full `ObjectDetail` — all
  sidebar fields), `GET /catalog/{id}/history`, `GET /catalog/{id}/state`,
  `GET /state/latest`, `GET /state/stream` (SSE), `GET /alerts/stream` (SSE).
  Generated TS client in `packages/shared-types`.
- Frontend ([apps/web/src/app](../apps/web/src/app)) is still the lynx shell:
  - `Components/CesiumComponent.tsx` renders **one `Entity` +
    `SampledPositionProperty` per TLE** → will not scale (dev-plan §4.3).
  - `lib/orbital-engine.ts` only calls `/catalog`, ignoring the generated client
    and the new endpoints.
  - No selection state, sidebar, search/filter tools, or Web Worker; default
    Cesium widgets still shown.

## Cross-cutting decisions (locked, per dev-plan §4)

- **Rendering migration is mandatory (§4.3):** full catalog →
  `PointPrimitiveCollection`; reserve `Entity` + `SampledPositionProperty`
  (orbit / ground-track) for the **selected/tracked** handful only.
- **SSR meaning (§4.1):** RSC renders shell + catalog metadata + initial result
  set; positional data streams as a compact payload — never per-satellite HTML.
- **Propagation source of truth (§4.2):** Python engine authoritative; browser
  satellite.js is display interpolation only.
- **AGPL hygiene (§4.7):** keeptrack tools (#9a–#9g, #9i) are **reference only**
  — rebuilt fresh in React. The info sidebar (#9h) reuses project-lynx2 (MIT).

## Branch sequence (Git flow — each branch off `develop`, merged back via PR)

| # | Branch | Scope | Depends on |
|---|---|---|---|
| 1 | `feature/stage-3-render-migration` | `PointPrimitiveCollection` batch render; click-pick selection + highlight; selected-object orbit/ground-track via `Entity`; hide superfluous Cesium widgets | — |
| 2 | `feature/stage-3-bff-catalog` | Selected-satellite React Context + dashboard shell — lift selection out of the globe so sibling panels can read/set it. BFF client/route extensions land with their consumers (branches 3–4), where they aren't speculative | 1 |
| 3 | `feature/stage-3-info-sidebar` | Per-satellite info sidebar (#9h) on `/catalog/{id}` — Current Position / Orbital Velocity / Orbital Parameters / Detailed Elements (project-lynx2 MIT); adds BFF `/api/catalog/[id]` proxy + `fetchObjectDetail` | 2 |
| 4 | `feature/stage-3-catalog-search` | Catalog search (#9a) + parametric find-sat (#9b) over `/catalog` | 2 |
| 5 | `feature/stage-3-filters` | Countries (#9d) + constellations (#9e) listing/selection; watchlist (#9f) | 2 |
| 6 | `feature/stage-3-sensors-passes` | Sensor list & selection (#9c) + pass-time / look-angle tool (#9i); needs sensor-site dataset | 2 |
| 7 | `feature/stage-3-webworker-stream` | Web Worker client-side display propagation; consume `/state/stream` SSE (authoritative state every N s, interpolate between) | 1, 2 |
| 8 | `feature/stage-3-collisions` | Conjunction browse & search (#9g) — UI built, backed by Stage-4 screening (stub until Stage 4 lands) | 2 |
| 9 | `feature/stage-3-load-test` | 10k–30k render load test (FPS/memory), SSR/stream payload budget, globe visual regression | 1, 7 |

General-UX items (2D/3D toggle, time controls, dark operational theme) land
incrementally across branches 1–3 where the surrounding code is already touched.

## Per-branch success criteria

- **1:** Catalog renders as GPU primitives (not per-object entities); left-click
  selects an object and highlights it; selected object shows an animated orbit;
  default home/help/fullscreen/geocoder widgets hidden. `typecheck` + `build`
  green.
- **2:** Selection state shared via context; clicking the globe updates context
  selection (consumed by the sidebar in branch 3); page renders from the engine
  (main.json = fallback only). `typecheck` + `build` green.
- **3:** Clicking an object opens a sidebar with the four field groups from live
  `/catalog/{id}`.
- **4:** Text/ID search and parametric (regime/inclination/period) search filter
  the rendered set.
- **5:** Filter/colour by nation and constellation; per-object watchlist persists.
- **6:** Active-sensor selection drives coverage; observer-relative pass list
  (az/el/range, rise/set).
- **7:** Smooth motion between server state updates; main thread not blocked at
  10k objects.
- **8:** Sortable conjunction list with drill-down to globe geometry (live once
  Stage 4 screening exists).
- **9:** ≥10k objects at interactive frame rate; documented payload budget;
  visual-regression baseline.

## Out of scope (later stages)

Conjunction screening engine (Stage 4), security/ABAC (Stage 5), maneuver/RPO
intelligence + explainability UI (Stage 6), ML (Stage 7).
