## Repository architecture overview

This document describes the high‑level structure of the project so that changes can be placed in the correct locations.

---

### 1. Technology stack

- **Framework**: Next.js (App Router, TypeScript)
- **UI**: React function components
- **3D / Map**: Cesium
- **Build & tooling**:
  - `npm run dev` – development server (also copies Cesium assets)
  - `npm run build` – production build (also copies Cesium assets)
  - `npm run lint` – linting via Next.js/ESLint configuration

Cesium assets are copied into `public/cesium` via the `copy-cesium` script referenced in `package.json`.

---

### 2. Directory structure (high level)

- `src/app/`
  - entry point and route hierarchy for the Next.js App Router.
  - `layout.tsx`: root layout, global HTML structure, global CSS import.
  - `page.tsx`: main page that renders the primary content.
  - `Components/`: React components used by pages, including Cesium integration components.
- `public/`
  - static assets served by Next.js, including the copied Cesium build under `public/cesium`.
- `docs/`
  - this documentation system (skills, guardrails, architecture, etc.).
- `.github/`
  - AI entrypoint configuration (`copilot-instructions.md`) and, optionally, task reports.

---

### 3. Application architecture

- **App shell**
  - Defined by `src/app/layout.tsx` using the Next.js App Router conventions.
  - Responsible for common HTML structure and global styling.

- **Pages and routes**
  - Each route under `src/app` corresponds to a page, optionally with its own layout.
  - Pages compose UI from shared and feature‑specific components.

- **Cesium integration**
  - Isolated in dedicated React components under `src/app/Components` (e.g. a Cesium viewer component).
  - These components:
    - own the lifecycle of Cesium viewer instances
    - connect to data sources and UI controls via props/state.

---

### 4. Data flow

- Data should:
  - flow top‑down via props or clearly defined context/providers.
  - be fetched in predictable locations (page/server components or dedicated hooks/utilities), then passed into UI/Cesium components.
- Cesium‑specific data transformations should live close to the Cesium integration components, not scattered across unrelated modules.

---

### 5. Validation and build pipeline

- Standard commands:
  - `npm run lint`
  - `npm run build`
- For development:
  - `npm run dev` should:
    - serve the main app
    - ensure Cesium assets are available under `public/cesium`.

Any changes to this pipeline should be treated as **Tooling / Configuration** tasks and documented in `docs/DECISIONS.md` and/or `docs/WORKFLOW.md`.

---

### 6. Evolution

- This file is a **living document**.
- When:
  - new modules or layers are introduced
  - routing structure changes significantly
  - Cesium integration is reorganized
  - new shared abstractions are added
- update this document to describe the new architecture so future changes remain aligned.

