## Guardrails for AI changes

These are **hard safety rules** for AI (and humans) working in this repository.
They apply to all tasks unless the GitHub Issue explicitly overrides them.

---

### 1. Scope and minimal change

- Prefer the **smallest safe change** that fully addresses the issue.
- Do not:
  - refactor unrelated code
  - “clean up” styles, naming, or structure that the issue does not mention
  - introduce new patterns or libraries without clear justification.
- If you discover unrelated problems, note them for a follow‑up issue instead of fixing them inline.

---

### 2. Respect existing patterns and architecture

- Follow the patterns documented in:
  - `docs/ARCHITECTURE.md`
  - `docs/DECISIONS.md`
  - `docs/STYLES.md`
- Mirror existing approaches in nearby code before inventing a new one.
- Do not change core architectural boundaries or state management patterns unless the issue is explicitly an **Architecture / Design Change**.

---

### 3. Validation is mandatory

- After code changes, you **must**:
  - follow the **Repository Validation** skill
  - at minimum run:
    - `npm run lint`
    - `npm run build`
- Do not consider a task complete if these commands fail, unless the issue states they are expected to fail and you are doing partial remediation.

---

### 4. Cesium integration safety

- When modifying Cesium behavior:
  - use the **Cesium Viewer Change** skill
  - ensure the viewer still initializes without errors
  - avoid leaking Cesium resources (clean up on unmount).
- Do not:
  - change how Cesium assets are loaded or copied without also updating relevant tooling docs and configs
  - introduce breaking changes to Cesium behavior outside the issue scope.

---

### 5. No speculative dependencies or tools

- Do not add new dependencies, tools, or build steps unless:
  - the issue explicitly calls for them, or
  - there is no reasonable solution with existing tooling.
- When adding dependencies:
  - choose widely used, well‑maintained packages
  - document the decision in `docs/DECISIONS.md`.

---

### 6. Backwards compatibility and breaking changes

- Treat changes as **backwards‑compatible by default**.
- If a breaking change is required:
  - ensure the issue explicitly calls for it, or
  - clearly document the impact in the PR description.

---

### 7. Documentation alignment

- When behavior, workflows, or architecture change:
  - update affected docs using the **Documentation Update** skill.
- Do not leave docs knowingly out of sync with the code.

---

### 8. Transparency in pull requests

- PRs should:
  - clearly state what changed and why
  - list validation steps run and their results
  - mention any deviations from these guardrails and why they were necessary.

