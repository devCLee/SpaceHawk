"""Eval runner for the daily-report Korean prose sections.

SKIPS (no-op, exit 0) when ``REPORT_LLM_API_KEY`` is unset, so CI without a key
passes untouched. With a key it makes a LIVE call through the configured provider
and applies the checks described in this directory's README (no stray numerals,
section register, length bounds) against ``baseline/``.

This file is intentionally minimal: the orchestrator captures the real baseline
on the first keyed run. Run directly, not under pytest.
"""

from __future__ import annotations

import os
import sys

# Sane character bounds per section (qualitative prose, not empty, not an essay).
_MIN_CHARS = 20
_MAX_CHARS = 2000


def main() -> int:
    if not os.environ.get("REPORT_LLM_API_KEY"):
        print("[daily_report_prose] REPORT_LLM_API_KEY unset - skipping live eval.")
        return 0

    # Imports are deferred so the skip path needs no heavy deps.
    from datetime import UTC, date, datetime

    from orbital_engine.config import get_settings
    from orbital_engine.reports.narrative import write_report_prose
    from orbital_engine.reports.sanitize import (
        LLMConjunctionFact,
        LLMFacts,
        LLMObjectFact,
        SanitizeResult,
    )

    settings = get_settings()

    # Minimal representative facts; the orchestrator swaps in a real fixture when
    # it captures the baseline. Tokens carry digits on purpose (guard exercise).
    facts = LLMFacts(
        report_date=date.today(),
        objects=[
            LLMObjectFact(token="OBJ-1", regime="LEO", object_type="PAYLOAD"),
            LLMObjectFact(token="OBJ-2", regime="LEO", object_type="DEBRIS"),
        ],
        conjunctions=[
            LLMConjunctionFact(
                primary_token="OBJ-1",
                secondary_token="OBJ-2",
                miss_distance_km=0.4,
                probability=1e-4,
                tca=datetime.now(UTC),
                alert_level="HIGH",
            )
        ],
    )
    sr = SanitizeResult(facts=facts, alias_map={"OBJ-1": "SH:CAT:1", "OBJ-2": "1998-067A"})

    prose = write_report_prose(sr, settings=settings)

    failures: list[str] = []
    for section, text in prose.items():
        n = len(text)
        if n < _MIN_CHARS or n > _MAX_CHARS:
            failures.append(f"{section}: length {n} out of bounds [{_MIN_CHARS}, {_MAX_CHARS}]")

    for line in (f"--- {s} ---\n{t}\n" for s, t in prose.items()):
        print(line)

    if failures:
        for f in failures:
            print(f"[FAIL] {f}", file=sys.stderr)
        return 1

    print("[daily_report_prose] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
