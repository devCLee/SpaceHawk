## Skill: Data Fetching

### Purpose

Add or modify data loading, transformation, and flow into React components or the Cesium viewer in a predictable and minimal way.

### When to use this skill

- The issue is about:
  - loading data from an API or file
  - changing when or how data is fetched
  - adjusting how data is passed into components or the Cesium viewer

### When *not* to use this skill

- For purely visual tweaks with no data changes → use **UI Change**.
- For Cesium configuration that does not alter data sources → use **Cesium Viewer Change**.
- For toolchain configuration of APIs or environment variables → use **Tooling / Configuration**.

---

### Procedure

1. **Identify data boundaries**
   - Locate where data is currently:
     - fetched (API calls, static files, etc.)
     - stored (state, props, context)
     - consumed (components, Cesium entities)
   - If no existing pattern exists, prefer:
     - keeping fetch logic close to the component that needs it, or
     - using established data utilities if present in the repo.

2. **Define the data contract**
   - Clarify:
     - what shape the data must have
     - how often it should be refreshed
     - how failures should be handled (basic error states, fallbacks)
   - Avoid over‑generalizing; design only for the current, explicit use case.

3. **Implement or adjust fetching**
   - Use existing HTTP/client utilities if available; otherwise use the project’s standard approach (e.g. `fetch`).
   - Keep side effects contained:
     - use established React patterns (hooks, server components, etc.) according to the repo’s architecture.
   - Avoid introducing new global state management libraries unless explicitly requested.

4. **Wire data into consumers**
   - Pass data via props or context using existing patterns.
   - For Cesium:
     - transform raw data into the minimal structure required to create or update entities/layers.
     - keep transformations near the boundary where data meets Cesium code.

5. **Handle loading and error states**
   - Provide clear but minimal UI for:
     - loading (spinners/placeholders)
     - errors (fallback message, logging if appropriate)
   - Follow existing stylistic and UX patterns from similar components.

6. **Run validation**
   - Apply the **Repository Validation** skill:
     - run `npm run lint`
     - run `npm run build`
   - If data fetching is critical, consider a quick manual check via `npm run dev`.

---

### Related skills

- `SKILL-CESIUM-VIEWER-CHANGE.md`
- `SKILL-UI-CHANGE.md`
- `SKILL-REPOSITORY-VALIDATION.md`

### Related documentation

- `docs/ARCHITECTURE.md` (data flow section)
- `docs/DECISIONS.md` (data layer conventions, if defined)

