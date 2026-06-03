## Skill: Architecture / Design Change

### Purpose

Perform higher‑impact structural or architectural changes while preserving intentional design decisions and respecting guardrails.

### When to use this skill

- The issue explicitly calls for:
  - reorganizing how Cesium is integrated
  - introducing new core abstractions or shared modules
  - changing state management or cross‑cutting patterns
  - modifying major boundaries in the Next.js app structure

### When *not* to use this skill

- For small, localized fixes that can be handled as:
  - **UI Change**
  - **Cesium Viewer Change**
  - **Data Fetching**
  - **Routing Change**
  - **Tooling / Configuration**
  - Prefer the smallest applicable skill and avoid unnecessary architectural work.

---

### Procedure

1. **Load architectural context**
   - Read:
     - `docs/ARCHITECTURE.md`
     - `docs/DECISIONS.md`
     - `docs/GUARDRAILS.md`
   - Identify:
     - existing module boundaries
     - intentional patterns and anti‑patterns
     - constraints you must not break.

2. **Clarify the problem and scope**
   - From the issue, distill:
     - the specific pain points or limitations in the current design
     - success criteria for the new design
     - explicit out‑of‑scope areas.

3. **Propose a minimal architecture change**
   - Design the smallest change that:
     - solves the problem
     - fits within existing decisions, or clearly and intentionally evolves them.
   - Avoid “big bang” rewrites; prefer incremental steps where possible.

4. **Plan the implementation**
   - Identify:
     - which files and modules will be touched
     - migration steps (e.g. temporary adapters, compatibility layers)
     - potential risks and how to mitigate them.

5. **Implement in small, verifiable steps**
   - Break work into coherent pieces that:
     - compile and pass validation where possible
     - can be reviewed independently.
   - Keep the codebase in a working state between steps whenever feasible.

6. **Update documentation**
   - After code changes, update:
     - `docs/ARCHITECTURE.md` to reflect new structure
     - `docs/DECISIONS.md` with rationale for major choices
     - any affected skill docs or workflow steps.
   - Use the **Documentation Update** skill.

7. **Run thorough validation**
   - Apply the **Repository Validation** skill:
     - run `npm run lint`
     - run `npm run build`
   - When practical, run a manual smoke test across key routes and Cesium flows.

---

### Related skills

- `SKILL-REPOSITORY-VALIDATION.md`
- `SKILL-DOCS-UPDATE.md`
- Other skills that apply to individual steps (UI, data, routing, tooling).

### Related documentation

- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md`
- `docs/GUARDRAILS.md`
- `docs/WORKFLOW.md`

