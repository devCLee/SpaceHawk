## Task workflow for this repo

This document describes the standard lifecycle for working on a task with AI assistance.

---

### 1. Start from the GitHub Issue or User prompt

- Read the issue end‑to‑end.
- Extract:
  - goal and acceptance criteria
  - constraints and non‑goals
  - any hints about architecture, performance, or UX.

---

### 2. Classify the task

- Open `docs/TASK-CLASSIFICATION.md`.
- Choose the **single best** category; note secondary categories if needed.
- This determines which skills to load next.

---

### 3. Load relevant skills

- Open `docs/SKILLS.md`.
- For the chosen category, open the referenced skill documents under `docs/skills/`.
- Read their procedures fully and follow them for the implementation.

---

### 4. Plan a minimal change

- Identify:
  - the files and modules likely involved
  - existing patterns to follow (from `docs/ARCHITECTURE.md`, `docs/STYLES.md`, `docs/DECISIONS.md`).
- Design the **smallest safe change** that satisfies the issue.
- Avoid mixing unrelated refactors or cleanups into the same change.

---

### 5. Implement the change

- Make focused edits guided by the loaded skills.
- Prefer:
  - localizing changes to feature‑specific components
  - reusing established patterns for UI, data, routing, and Cesium.

---

### 6. Run validation

- Apply the **Repository Validation** skill:
  - run `npm run lint`
  - run `npm run build`
- If the change affects key flows (e.g. main page, Cesium viewer), optionally:
  - run `npm run dev`
  - perform a quick manual smoke test.

---

### 7. Review documentation impact

- Ask whether behavior, workflows, or architecture changed in a way that documentation should reflect.
- If yes, use the **Documentation Update** skill to adjust:
  - `README.md`
  - relevant files under `docs/` (architecture, decisions, skills, etc.).

---

### 8. Prepare a pull request

- Follow `docs/workflow/WORKFLOW-PRS.md` for:
  - branch naming and commit messages
  - PR description structure
  - required validation evidence.

---

### 9. Iterate based on feedback

- When review comments arrive:
  - treat them as new, small tasks
  - apply the same workflow (classify → skills → minimal change → validation), scaled to the size of the requested change.

