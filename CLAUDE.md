# SpaceHawk — Project Instructions

## Context Navigation

1. ALWAYS query the knowledge graph first
2. Only read raw files if I explicitly say so
3. Use graphify-out/GRAPH_REPORT.md

## Working principles

These four principles bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think before coding

Don't assume. Don't hide confusion. Surface tradeoffs. Before implementing, state assumptions explicitly; if uncertain, ask. If multiple interpretations exist, present them — don't pick silently. If something is unclear, stop and name what's confusing.

### 2. Simplicity first

Minimum code that solves the problem. Nothing speculative. No features beyond what was asked. No abstractions for single-use code. No "flexibility" or "configurability" that wasn't requested. No error handling for impossible scenarios.

### 3. Surgical changes

Touch only what you must. Don't "improve" adjacent code, comments, or formatting. Don't refactor things that aren't broken. Match existing style. Every changed line should trace directly to the user's request.

### 4. Goal-driven execution

Define success criteria, then loop until verified. "Add validation" → "Write tests for invalid inputs, then make them pass." Strong success criteria let you loop independently.

## Stack

Next.js 16 (App Router) · React 19 · TypeScript · Prisma 7 · Supabase · Radix UI · Tailwind CSS 4 · TanStack Query · Lexical editor.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

**Planning & strategy (gstack, global):**

- Product ideas / brainstorming → `/office-hours`
- Strategy / scope → `/plan-ceo-review`
- Architecture → `/plan-eng-review`
- Design system / plan review → `/design-consultation` or `/plan-design-review`
- Full review pipeline → `/autoplan`

**Development (gstack, global):**

- Bugs / errors → `/investigate`
- QA / testing site behavior → `/qa` or `/qa-only`
- Code review / diff check → `/review`
- Visual polish → `/design-review`
- Ship / deploy / PR → `/ship` or `/land-and-deploy`
- Save progress → `/context-save`
- Resume context → `/context-restore`

**Project skills (`.claude/skills/`):**

- Explain code with mental models → `/explain`
- Refactor with tests as safety net → `/refactor`
- TDD red-green-refactor → `/tdd`
- Auto-write tests for new code → `/test-writer`
- Emergency production fix → `/hotfix`
- Locate and fix bugs with regression tests → `/debug-fix`

**Project commands (`.claude/commands/`):**

- Deep task exploration → `/onboard`
- Implement a JIRA/Linear ticket → `/ticket`
- Generate PR description → `/pr-summary`
- Run quality checks → `/code-quality`
- Sync documentation → `/docs-sync`

**PM skills (`.claude/skills/`):**

- Validate a product idea → `/idea-validator`
- Write a LinkedIn post → `/linkedin-post-writer`
- Improve a prompt → `/prompt-engineer`
- Design review → `/product-designer`
- Stakeholder status update → `/status-update-writer`

**Auto-triggered skills (model-invocation):**

- `karpathy-guidelines` — coding discipline reminders
- `testing-patterns` — Jest patterns, factories, TDD
- `react-ui-patterns` — loading states, error handling, hooks
- `core-components` — design system tokens
- `systematic-debugging` — four-phase debugging methodology

## Agents (`.claude/agents/`)

- `code-reviewer` — correctness and maintainability review
- `security-reviewer` — injection, auth, crypto static analysis
- `performance-reviewer` — real bottleneck identification
- `frontend-designer` — production UI without "AI slop"
- `doc-reviewer` — verifies docs against source code
- `github-workflow` — git operations and PR management

## Rules (`.claude/rules/`)

Project-specific guidelines for:

- `code-quality.md`
- `database.md` (Prisma + Supabase)
- `error-handling.md`
- `frontend.md` (React/Next.js)
- `security.md`
- `testing.md`

## Hooks

`.claude/settings.json` wires up automatic guards:

- **PreToolUse** on Edit/Write — protects sensitive files (`.env`, keys), warns on large files, scans for secrets
- **PreToolUse** on Bash — blocks dangerous commands
- **PostToolUse** on Edit/Write — auto-formats with Prettier
- **SessionStart** — loads project context
