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

### How to add new decisions

When you make a new intentional choice that will affect future work:

1. Add a new section with:
   - **Decision**
   - **Rationale**
   - **Implications**
2. Keep entries concise and focused on long‑term behavior and constraints.

