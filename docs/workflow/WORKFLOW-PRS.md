## Pull request workflow

This document defines how to prepare and structure pull requests for this repository.

---

### 1. Branching

- Create a feature branch from the main development branch.
- Use a clear, kebab‑case name that hints at the task, for example:
  - `feature/cesium-camera-tweak`
  - `fix/home-page-layout`
  - `chore/update-deps`.

---

### 2. Commits

- Keep commits small and focused.
- Commit messages should:
  - start with a concise verb (e.g. `add`, `fix`, `update`, `refactor`)
  - briefly describe the intent (e.g. `add zoom controls to Cesium viewer`).
- Avoid mixing unrelated changes in a single commit.

---

### 3. PR description

Include the following sections in the pull request description:

- **Summary**
  - 2–5 bullet points describing what changed and why.
- **Motivation / Context**
  - Link to the GitHub Issue.
  - Briefly explain how the change addresses it.
- **Validation**
  - List all commands run (e.g. `npm run lint`, `npm run build`).
  - State whether each command passed.
  - Note any manual checks (e.g. “Verified Cesium viewer loads and new interaction works on `/`”).
- **Documentation**
  - List any docs updated (or state “No documentation changes required”).

---

### 4. Scope and safety checks

- Confirm that:
  - changes are limited to the issue’s scope
  - there are no drive‑by refactors or unrelated cleanups.
- If you had to make broader changes:
  - call them out explicitly
  - explain why they were necessary.

---

### 5. Ready for review checklist

Before marking a PR as ready for review, ensure:

- [ ] All relevant skills from `docs/SKILLS.md` were followed.
- [ ] `npm run lint` has been run and passes (or failures are explained).
- [ ] `npm run build` has been run and passes (or failures are explained).
- [ ] Any significant behavior changes have been manually sanity‑checked where practical.
- [ ] Documentation is updated, if needed.

---

### 6. Responding to review

- Treat each review comment as a small follow‑up task.
- Apply the same principles:
  - minimal change
  - validation after adjustments
  - update docs or PR description if the scope shifts.

