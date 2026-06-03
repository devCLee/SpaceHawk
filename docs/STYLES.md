## Coding and style conventions

These conventions guide how new code and UI should be written in this repository.

---

### 1. General coding style

- Use **TypeScript** for all new code.
- Prefer **function components** with hooks over class components.
- Follow the project’s ESLint configuration; do not fight or disable rules unless strictly necessary.
- Keep functions and components small and focused on a single responsibility.

---

### 2. React and Next.js patterns

- Organize code by **feature/route** under `src/app`, using Next.js App Router conventions.
- Compose UI from smaller components rather than building very large pages.
- Prefer explicit props over implicit globals; keep shared logic in well‑named utilities or hooks when patterns repeat.

---

### 3. Cesium integration

- Keep Cesium‑specific logic inside dedicated components or helpers, not mixed arbitrarily into unrelated UI.
- Clearly separate:
  - configuration (camera, imagery, terrain)
  - data (entities, overlays)
  - interaction logic (event handlers).
- Clean up Cesium resources on unmount to avoid leaks.

---

### 4. Naming conventions

- Use **descriptive, domain‑relevant names** for components and variables.
- Components: `PascalCase` (e.g. `CesiumViewer`, `MainPage`).
- Variables and functions: `camelCase` (e.g. `initialCameraPosition`, `loadSceneData`).
- Avoid abbreviations that are not obvious to a new contributor.

---

### 5. Styling conventions

- Follow existing styling patterns in the repo (e.g. global CSS, CSS modules) rather than introducing new systems without discussion.
- Keep styles:
  - scoped appropriately to components
  - readable and maintainable (avoid deeply nested selectors where possible).
- When adjusting styles, avoid large rewrites outside the scope of the issue.

---

### 6. Comments and documentation in code

- Use comments to explain **why**, not **what** (the code already shows what).
- Document non‑obvious constraints (e.g. Cesium quirks, performance considerations).
- Avoid excessive inline commentary that restates obvious behavior.

---

### 7. Error handling and logging

- Fail fast with clear messages where appropriate, especially around data fetching and Cesium initialization.
- Do not introduce noisy logging in hot paths; prefer targeted logging that helps debug real issues.

---

### 8. Evolving styles

- When new patterns prove useful, reflect them here so they can be reused consistently.
- Keep this file concise; link to examples in the codebase when they exist instead of duplicating large snippets.

