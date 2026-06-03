## Skill index for this repo

Use this file **after** classifying the task in `docs/TASK-CLASSIFICATION.md`.

1. Find the skill(s) that match your task category.
2. Open the referenced file(s) under `docs/skills/`.
3. Follow the procedures and validation steps in those skill documents.

This index is intentionally concise; detailed procedures live in the individual skill files.

---

### Skill: UI Change

- **Description**: Modify React UI, layout, or styling (excluding Cesium scene internals) in a safe, minimal way.
- **Use when**: The primary change concerns text, layout, components, accessibility, or styles.
- **Reference**: `docs/skills/SKILL-UI-CHANGE.md`

---

### Skill: Cesium Viewer Change

- **Description**: Adjust Cesium viewer behavior, entities, camera, or map‑related UI safely.
- **Use when**: The main focus is how the Cesium scene renders or responds to user interaction.
- **Reference**: `docs/skills/SKILL-CESIUM-VIEWER-CHANGE.md`

---

### Skill: Data Fetching

- **Description**: Introduce or modify data loading, transformation, or flow into components or the Cesium viewer.
- **Use when**: The task is about where data comes from and how it reaches the UI/scene.
- **Reference**: `docs/skills/SKILL-DATA-FETCHING.md`

---

### Skill: Routing Change

- **Description**: Change Next.js routing, pages, or layouts while preserving app behavior and conventions.
- **Use when**: The task involves URLs, page structure, or how the app shell is composed.
- **Reference**: `docs/skills/SKILL-ROUTING-CHANGE.md`

---

### Skill: Tooling / Configuration

- **Description**: Safely modify project tooling, scripts, or configuration files (Next.js, TypeScript, Cesium build steps, linting).
- **Use when**: The change affects how the project builds, runs, or is linted/tested rather than runtime UI behavior.
- **Reference**: `docs/skills/SKILL-TOOLING-CONFIG.md`

---

### Skill: Documentation Update

- **Description**: Update documentation files so they remain accurate, concise, and aligned with the codebase.
- **Use when**: The task is docs‑only or includes a required documentation update alongside code changes.
- **Reference**: `docs/skills/SKILL-DOCS-UPDATE.md`

---

### Skill: Repository Validation

- **Description**: Run and interpret validation commands for this repo (lint, build, and any additional checks), and react to failures safely.
- **Use when**: Any task requires confirming the repository is healthy after changes.
- **Reference**: `docs/skills/SKILL-REPOSITORY-VALIDATION.md`

---

### Skill: Architecture / Design Change

- **Description**: Perform higher‑impact structural or architectural changes while respecting existing decisions and guardrails.
- **Use when**: The issue explicitly calls for changing core structure, abstractions, or cross‑cutting patterns.
- **Reference**: `docs/skills/SKILL-ARCHITECTURE-CHANGE.md`

