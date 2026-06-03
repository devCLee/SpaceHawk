## Skill: Routing Change

### Purpose

Modify Next.js routing, pages, and layouts while preserving expected URLs, metadata, and integration with the Cesium viewer.

### When to use this skill

- The issue involves:
  - adding, renaming, or removing pages under `src/app`
  - changing layouts, metadata, or the root layout
  - moving where the Cesium viewer is mounted within the app routing structure

### When *not* to use this skill

- For pure UI or styling changes on an existing page → use **UI Change**.
- For Cesium behavior within a page without routing changes → use **Cesium Viewer Change**.
- For build configuration of Next.js itself → use **Tooling / Configuration**.

---

### Procedure

1. **Map current routes**
   - Inspect `src/app` to understand:
     - existing route segments and page components
     - layout hierarchy (e.g. `layout.tsx`)
     - where the Cesium viewer currently lives (if applicable).

2. **Understand requested routing behavior**
   - From the issue, extract:
     - desired URLs
     - which component(s) should render for each route
     - any metadata/SEO requirements (titles, descriptions, OG tags).

3. **Plan minimal structural changes**
   - Prefer:
     - adding or modifying the smallest number of files
     - reusing existing layouts and wrappers when possible
   - Avoid large reorganizations unless explicitly requested as an architecture change.

4. **Implement routing adjustments**
   - Add/modify/remove page or layout files as required by Next.js conventions for the version used in this repo.
   - Ensure imports and exports remain consistent and type‑safe.
   - If moving the Cesium viewer:
     - keep initialization patterns consistent
     - verify that any required providers or context wrappers still apply.

5. **Check backwards compatibility**
   - If any routes are changed or removed:
     - confirm whether redirects or fallbacks are needed.
     - note breaking changes clearly in the PR description.

6. **Run validation**
   - Apply the **Repository Validation** skill:
     - run `npm run lint`
     - run `npm run build`
   - Optionally, run `npm run dev` and verify that key routes load as expected.

---

### Related skills

- `SKILL-UI-CHANGE.md`
- `SKILL-CESIUM-VIEWER-CHANGE.md`
- `SKILL-REPOSITORY-VALIDATION.md`

### Related documentation

- `docs/ARCHITECTURE.md` (routing structure)
- `docs/DECISIONS.md` (routing conventions, if defined)

