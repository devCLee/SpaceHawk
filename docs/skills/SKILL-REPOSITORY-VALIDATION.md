## Skill: Repository Validation

### Purpose

Ensure the repository is in a healthy state after changes by running the standard validation commands and responding safely to failures.

### When to use this skill

- After **any** code or documentation change before considering the task complete.
- Before preparing a pull request.
- When an issue explicitly mentions build, lint, or tooling problems.

### When *not* to use this skill

- Never skip this skill for code changes unless the issue explicitly states that validation is temporarily expected to fail and you should only make a partial fix.

---

### Procedure

1. **Understand expected validation**
   - From `.github/copilot-instructions.md` and `docs/WORKFLOW.md`, note that default validation includes:
     - `npm run lint`
     - `npm run build`
   - If `docs/WORKFLOW.md` or other docs list additional checks (e.g. tests), include them as well.

2. **Run lint**
   - Execute: `npm run lint`
   - If it **succeeds**:
     - Note in your summary/PR that lint passed.
   - If it **fails**:
     - Read the error output carefully.
     - Prefer **minimal changes** that fix only the reported issues.
     - Do not introduce style refactors beyond what the linter requires.
     - Re‑run `npm run lint` until it passes or until you reach a clear stopping point with remaining known issues documented.

3. **Run build**
   - Execute: `npm run build`
   - If it **succeeds**:
     - Note in your summary/PR that build passed.
   - If it **fails**:
     - Identify whether failures are:
       - type errors (TypeScript)
       - module resolution issues
       - runtime build errors (e.g. misconfigured Cesium paths)
     - Apply the smallest safe fix that addresses the failure.
     - Avoid speculative refactors; prefer targeted corrections.
     - Re‑run `npm run build` until it succeeds or you have a clearly documented remaining issue.

4. **Manual sanity check (optional but recommended)**
   - If practical, run `npm run dev` locally and perform a quick smoke check:
     - load the main page
     - confirm the Cesium viewer still initializes (if applicable)
     - verify the changed UI behaves as expected
   - Capture any regressions as follow‑up issues rather than attempting large refactors inline.

5. **Record validation results**
   - In the pull request or task summary, clearly state:
     - commands run (e.g. `npm run lint`, `npm run build`)
     - whether they succeeded
     - any remaining known issues, linked to follow‑up work if applicable.

---

### Related documentation

- `.github/copilot-instructions.md`
- `docs/WORKFLOW.md`
- `docs/GUARDRAILS.md`

