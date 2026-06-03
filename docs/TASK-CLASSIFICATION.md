## Task classification for this repo

Use this document after reading the GitHub Issue and before loading skills.
Pick the **single closest category**; if a task spans multiple areas, choose the dominant one and note secondary categories.

For each category:
- follow the notes below, then
- open `docs/SKILLS.md` to find and load the referenced skills.

---

### 1. UI / Layout Change

Changes focused on visual structure, layout, or non‑Cesium UI components, for example:
- updating text, buttons, or layout in React components
- tweaking CSS or global styles
- minor accessibility improvements

When the issue is primarily about how the page looks or feels (outside of the Cesium viewer), classify as **UI / Layout Change**.

Recommended skills:
- `SKILL-UI-CHANGE.md`
- `SKILL-REPOSITORY-VALIDATION.md`

---

### 2. Cesium Viewer Behavior or Map UI

Changes primarily affecting the Cesium-based map experience, for example:
- modifying camera behavior or initial view
- adding/removing layers, imagery, or entities
- changing controls, interaction, or overlays around the viewer

If the issue’s core concern is how the Cesium scene behaves or renders, classify as **Cesium Viewer Behavior or Map UI**.

Recommended skills:
- `SKILL-CESIUM-VIEWER-CHANGE.md`
- `SKILL-UI-CHANGE.md` (if surrounding UI is also affected)
- `SKILL-REPOSITORY-VALIDATION.md`

---

### 3. Data Fetching / Data Flow

Changes focused on how data is loaded, transformed, or passed into components, for example:
- calling APIs to load data used in Cesium or UI
- adjusting props/state to flow data through the component tree
- adding simple client‑side caching or derived data

If the main question is “where does this data come from and how does it get into the UI or Cesium?”, classify as **Data Fetching / Data Flow**.

Recommended skills:
- `SKILL-DATA-FETCHING.md`
- `SKILL-REPOSITORY-VALIDATION.md`

---

### 4. Routing / Next.js Structure

Changes to the Next.js routing or app structure, for example:
- adding or removing pages under `src/app`
- changing layouts, metadata, or root layout behavior
- adjusting how Cesium is integrated into Next.js routing

If the issue touches URLs, page hierarchy, or app shell behavior, classify as **Routing / Next.js Structure**.

Recommended skills:
- `SKILL-ROUTING-CHANGE.md`
- `SKILL-REPOSITORY-VALIDATION.md`

---

### 5. Build / Tooling / Configuration

Changes to repository tooling or configuration, for example:
- updating `next.config.js` or TypeScript settings
- adjusting Cesium build / copy steps
- modifying lint, test, or script configuration in `package.json`

If the issue is about how the project builds, runs, or is tooled (not the runtime behavior of components), classify as **Build / Tooling / Configuration**.

Recommended skills:
- `SKILL-TOOLING-CONFIG.md`
- `SKILL-REPOSITORY-VALIDATION.md`

---

### 6. Documentation‑Only Change

Changes limited to documentation, for example:
- updating `README.md`
- editing files under `docs/` that do not require code changes
- improving comments or high‑level explanations

If no code change is expected, classify as **Documentation‑Only Change**.

Recommended skills:
- `SKILL-DOCS-UPDATE.md`
- `SKILL-REPOSITORY-VALIDATION.md` (to ensure docs still match reality when appropriate)

---

### 7. Repository Maintenance / Chore

Low‑risk maintenance tasks, for example:
- dependency bumps with no intended behavioral change
- simple file moves or renames that preserve behavior
- housekeeping in project structure that does not alter features

If the primary goal is to keep the repo healthy rather than add/change features, classify as **Repository Maintenance / Chore**.

Recommended skills:
- `SKILL-REPOSITORY-VALIDATION.md`
- `SKILL-TOOLING-CONFIG.md` (if tooling is involved)

---

### 8. Architecture / Design Change

High‑impact changes to how the app is structured or how major concerns are separated, for example:
- reorganizing Cesium integration boundaries
- introducing new shared abstractions or core libraries
- altering state management strategy or cross‑cutting patterns

Classify as **Architecture / Design Change** only when the issue explicitly calls for it.
These tasks require extra care:
- first read `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, and `docs/GUARDRAILS.md`
- then load the relevant skills listed in `docs/SKILLS.md` for architecture work.

Recommended skills:
- `SKILL-ARCHITECTURE-CHANGE.md`
- `SKILL-REPOSITORY-VALIDATION.md`

---

### 9. Ambiguous or Mixed Tasks

If the issue spans multiple categories or is unclear:
- pick the **dominant** category based on the primary acceptance criteria
- note any secondary categories in the PR description
- when in doubt between “Architecture / Design Change” and a smaller category, **default to the smaller category** and propose a follow‑up architecture issue if needed.

Then proceed to `docs/SKILLS.md` to load the skills associated with your chosen category.

