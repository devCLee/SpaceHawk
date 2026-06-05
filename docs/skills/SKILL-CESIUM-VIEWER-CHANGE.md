## Skill: Cesium Viewer Change

### Purpose

Safely adjust Cesium viewer behavior, entities, camera, or map‑related UI while preserving performance and existing integration with Next.js.

### When to use this skill

- The issue focuses on:
  - camera position, orientation, or movement
  - adding/removing/updating entities, imagery layers, or terrain
  - interaction behavior (click, hover, selection) within the Cesium scene
  - controls or overlays tightly coupled to the viewer

### When *not* to use this skill

- For general page layout or non‑map UI → use **UI Change**.
- For adding or changing data sources feeding Cesium → use **Data Fetching** as well.
- For build or configuration issues with Cesium assets → use **Tooling / Configuration**.

---

### Procedure

1. **Understand the current Cesium integration**
   - Locate the main Cesium component(s) (e.g. under `src/app/Components`).
   - Identify:
     - where the `Viewer` (or equivalent) is created
     - how entities/layers are added
     - how props/state influence the scene

2. **Clarify the requested behavior**
   - From the issue, extract:
     - what should change in the scene (camera, entities, layers, interaction)
     - any performance or UX constraints (e.g. smooth animation, initial zoom)
   - Decide whether the change is:
     - purely configuration (e.g. different initial camera)
     - structural (new entities, new helper functions)

3. **Plan a minimal, localized change**
   - Prefer adjusting existing configuration or helper functions over rewriting large sections.
   - If adding new behavior:
     - group related Cesium code into small, focused functions or components.
     - avoid introducing new global state unless necessary.

4. **Implement the Cesium change**
   - Update viewer/options, entities, or handlers as required.
   - Reuse established patterns for:
     - creating and cleaning up Cesium resources
     - handling effects and lifecycle (React hooks, if used)
   - Make sure all added resources are properly disposed of when components unmount.

5. **Coordinate with data and UI when needed**
   - If new data is required, also follow the **Data Fetching** skill.
   - If surrounding UI (buttons, panels) must change, also follow the **UI Change** skill.

6. **Manual verification (recommended)**
   - Run `npm run dev`.
   - Open the page that hosts the Cesium viewer.
   - Verify:
     - the viewer still initializes without console errors.
     - the new behavior matches the issue description.
     - performance remains acceptable.

7. **Run validation**
   - Apply the **Repository Validation** skill:
     - run `npm run lint`
     - run `npm run build`

---

### ⚠️ Imagery providers are coupled to the CSP

The app ships a strict Content-Security-Policy (`next.config.mjs`, Stage 5
hardening). Any imagery/terrain provider the viewer contacts must have its origin
allowlisted in `connect-src` (metadata + `fetch()`/`createImageBitmap` tiles) and
`img-src` (`<img>` tile fallback), or the browser blocks it and floods the console
with CSP violations.

- The online globe's `BaseLayerPicker` is **curated** to only Ion/Bing-hosted
  basemaps this token owns (`assets.ion.cesium.com` / `*.virtualearth.net` /
  same-origin) — built by filtering `createDefaultImageryProviderViewModels()` /
  `createDefaultTerrainProviderViewModels()` by name in `CesiumComponent.tsx`.
  Cesium's full default grid also offers ArcGIS / ESRI / OpenStreetMap / Stadia,
  but those hit third-party CDNs the strict CSP blocks, so they are excluded. Do
  NOT re-add them without widening the CSP and flagging the egress in
  `docs/design/STAGE-5-SECURITY-MEMO.md`.
- The **offline** globe keeps `baseLayerPicker: false` so an air-gapped enclave
  never attempts any CDN fetch.

Before adding a new imagery/terrain source: add its origin to the CSP in the same
change, and if it is a non-Ion third party, flag the egress in the security memo.

### Related skills

- `SKILL-DATA-FETCHING.md`
- `SKILL-UI-CHANGE.md`
- `SKILL-REPOSITORY-VALIDATION.md`

### Related documentation

- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md` (for Cesium integration choices)
- `docs/GUARDRAILS.md`

