## Skill: Tooling / Configuration

### Purpose

Safely modify project tooling and configuration (Next.js, TypeScript, Cesium asset handling, linting, scripts) while minimizing risk to builds and runtime behavior.

### When to use this skill

- The issue focuses on:
  - `next.config.js`, TypeScript config, or ESLint settings
  - NPM scripts in `package.json`
  - Cesium asset build/copy steps
  - CI or other build‑time configuration (if present)

### When *not* to use this skill

- For UI or component behavior changes → use **UI Change** or **Cesium Viewer Change**.
- For data flow logic → use **Data Fetching**.

---

### Procedure

1. **Understand the current tooling setup**
   - Review:
     - `package.json` scripts (e.g. `copy-cesium`, `dev`, `build`, `lint`)
     - `next.config.js` and any additional config files
   - Identify how Cesium assets are handled in this repo and avoid disrupting that flow without explicit need.

2. **Clarify the requested change**
   - From the issue, determine:
     - what problem is being solved (e.g. build failure, missing lint rule)
     - what behavior is expected after the change.

3. **Plan a minimal configuration update**
   - Prefer:
     - small, targeted edits over wholesale replacement of config files
     - reusing existing patterns from this repo or official Next.js/Cesium guidance.
   - Avoid introducing new tooling unless the issue explicitly requires it.

4. **Apply configuration changes**
   - Edit only the necessary config keys or scripts.
   - Keep comments and structure clear and consistent with existing style.
   - Ensure changes remain compatible with the project’s current Next.js and TypeScript versions.

5. **Run validation**
   - Apply the **Repository Validation** skill:
     - run `npm run lint`
     - run `npm run build`
   - If changes affect development workflow (e.g. dev server behavior), consider briefly running `npm run dev` to confirm expected behavior.

6. **Document notable changes**
   - If configuration changes alter:
     - how the app is built or deployed
     - how Cesium assets are handled
   - Update relevant documentation (e.g. `README.md`, `docs/WORKFLOW.md`, or `docs/DECISIONS.md`) using the **Documentation Update** skill.

---

### Related skills

- `SKILL-REPOSITORY-VALIDATION.md`
- `SKILL-DOCS-UPDATE.md`

### Related documentation

- `docs/WORKFLOW.md`
- `docs/DECISIONS.md` (tooling decisions)
- `docs/GUARDRAILS.md`

