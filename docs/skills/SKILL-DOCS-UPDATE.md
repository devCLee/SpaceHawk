## Skill: Documentation Update

### Purpose

Keep documentation accurate, concise, and aligned with the codebase when behavior, workflows, or architecture change.

### When to use this skill

- The task is documentation‑only.
- A code change modifies behavior, workflows, or architecture in a way that existing docs reference.
- New patterns or conventions are introduced that should be captured.

### When *not* to use this skill

- For pure code changes where no documented behavior or workflow changes; in these cases, still briefly confirm whether any docs should be updated, but avoid unnecessary edits.

---

### Procedure

1. **Identify affected docs**
   - From the issue and your code changes, list which docs might be impacted:
     - `README.md`
     - files under `docs/` (e.g. `ARCHITECTURE`, `DECISIONS`, `STYLES`, `WORKFLOW`, skills)
   - Prefer updating existing sections over adding new ones, unless there is a clear gap.

2. **Confirm current reality**
   - Inspect the relevant code paths to ensure you are documenting **actual behavior**, not intentions or guesses.
   - Avoid describing future or speculative work.

3. **Edit for clarity and minimality**
   - Use simple, direct language.
   - Keep documents focused on their purpose:
     - skills → procedures
     - architecture → structure and boundaries
     - decisions → rationale
     - workflow → lifecycle/task steps
   - Remove or adjust outdated statements instead of layering conflicting information.

4. **Cross‑reference where useful**
   - When you add or adjust a section that relies on other docs:
     - link to those docs (by file path) rather than duplicating details.

5. **Run validation**
   - If documentation changes accompany code changes, apply the **Repository Validation** skill.
   - For documentation‑only changes, ensure:
     - links and file paths you reference actually exist.

6. **Summarize documentation impact**
   - In the PR or task summary, clearly list:
     - which docs were updated
     - what aspect of behavior/workflow/architecture they reflect.

---

### Related skills

- `SKILL-REPOSITORY-VALIDATION.md`
- All other skills that led to behavior changes.

### Related documentation

- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md`
- `docs/STYLES.md`
- `docs/WORKFLOW.md`

