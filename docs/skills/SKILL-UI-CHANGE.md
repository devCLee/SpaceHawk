## Skill: UI Change

### Purpose

Safely modify React UI, layout, or styling (outside of Cesium scene internals) while respecting existing patterns and minimizing unintended side effects.

### When to use this skill

- The issue is primarily about:
  - text, buttons, or labels
  - layout adjustments
  - visual design tweaks
  - accessibility improvements
  - non‑Cesium UI components surrounding the viewer

### When *not* to use this skill

- When the main change is:
  - Cesium camera, entities, or map behavior → use **Cesium Viewer Change**.
  - Data loading or state/data flow → use **Data Fetching**.
  - Routing or page structure → use **Routing Change**.
  - Tooling or configuration only → use **Tooling / Configuration**.

---

### Procedure

1. **Locate existing patterns**
   - Find the component(s) mentioned in the issue (e.g. under `src/app`).
   - Look for similar components or UI patterns and mirror:
     - naming conventions
     - JSX structure
     - styling approach (CSS modules, global CSS, etc.)

2. **Plan the smallest safe change**
   - Identify which props, elements, or style rules must change.
   - Avoid renaming or moving components unless required by the issue.
   - Do not introduce new UI libraries or paradigms unless explicitly requested.

3. **Implement the change**
   - Update JSX and styles in a focused manner.
   - Prefer composition over duplication when reusing patterns.
   - Keep changes localized to the relevant component(s) when possible.

4. **Accessibility and UX checks**
   - Ensure interactive elements remain keyboard accessible.
   - Preserve or improve semantics (e.g. `button` vs `div` with click).
   - Avoid regressions in contrast or readability when altering styles.

5. **Update tests or docs if needed**
   - If the change alters visible behavior significantly, ensure:
     - any relevant documentation references are updated.
     - examples (if present) remain accurate.

6. **Run validation**
   - Apply the **Repository Validation** skill:
     - run `npm run lint`
     - run `npm run build`
   - Fix issues surfaced by these commands with minimally scoped changes.

---

### Related skills

- `SKILL-REPOSITORY-VALIDATION.md`
- `SKILL-CESIUM-VIEWER-CHANGE.md` (for viewer‑adjacent UI)

### Related documentation

- `docs/STYLES.md`
- `docs/ARCHITECTURE.md`
- `docs/GUARDRAILS.md`

