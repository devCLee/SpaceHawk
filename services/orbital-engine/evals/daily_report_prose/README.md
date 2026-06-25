# Eval: daily report prose (`daily_report_prose`)

Quality eval for the LLM-written Korean prose sections of the daily report
(개요 / 분석내용 / 향후추진), produced by
`orbital_engine.reports.narrative.write_report_prose`.

This eval makes a **live** call to the configured OpenAI-compatible provider, so
it runs only when `REPORT_LLM_API_KEY` is set. With no key (local dev / CI) the
runner is a no-op and exits 0 — the live baseline is captured later by the
orchestrator, not in unit CI.

## What it checks

Per generated section, against the committed `baseline/`:

1. **No stray numerals** — the same guard the production code enforces: after
   removing the anonymization tokens (OBJ-1 …), no bare `[0-9]` digit may remain.
   This is the load-bearing check (numbers are the template's job, not the LLM's).
2. **Section register** — output reads as formal Korean SDA-report prose for the
   requested section (qualitative, no invented identities), judged against the
   baseline sample for that section.
3. **Length bounds** — each section's prose stays within sane min/max character
   bounds (not empty, not a runaway essay).

## Layout

- `run_eval.py` — entry point. Skips (no-op, exit 0) when `REPORT_LLM_API_KEY`
  is unset. Otherwise builds facts, calls `write_report_prose`, and runs the
  checks above against `baseline/`.
- `baseline/` — committed reference prose per section. Currently a placeholder
  (`baseline/PLACEHOLDER.md`); the orchestrator captures the real baseline on the
  first keyed run.

## Run

```bash
# no key => skipped, exits 0
python evals/daily_report_prose/run_eval.py

# with a key => live baseline/eval run
REPORT_LLM_API_KEY=... REPORT_LLM_BASE_URL=... python evals/daily_report_prose/run_eval.py
```
