# Stage 6 — Validated Intelligence: maneuver detection, RPO, classification, fingerprinting

*(Dev-plan Stage 6 → roadmap P2a; M6–M11, parallel with Stages 2–5 tail. Features #10–#14 + explainable-intent UI.)*

## Objective

The validated (TRL 5–6) analytic core on TLE/element-set data, plus the
explainability/fingerprinting differentiators (roadmap O4 "innovation spine").
Reuses the Stage-2 pipeline/DB — most of all the `gp_history` element-set
hypertable — so it runs largely in parallel with the Phase-1 tail.

## Starting point (verified on `develop`)

- Stages 0–5 merged. Engine has ingestion (Space-Track / Celestrak / DISCOS /
  Leolabs / CDM), server SGP4, conjunction screening + trust-calibrated alerting,
  the durable alert log + `ConjunctionAlerter`, and Stage-5 ABAC/audit.
- `gp_history` (TimescaleDB hypertable, migration `0001`) already stores one row
  per `(object_id, epoch)` of mean elements — the maneuver/RPO substrate. Written
  by `repository.append_history` on every ingest; read by `repository.fetch_history`.
- `security.attributes.DataDomain.MANEUVER_INTEL` is already reserved in the ABAC
  vocabulary (P0-RBAC-ABAC §2) for this stage's endpoints.
- Codebase ethos: **minimal dependencies** (`docs/DECISIONS.md`) — the engine uses
  stdlib `math`/`statistics`, not NumPy/SciPy. Stage 6 keeps that: detection,
  Δv, RIC and the behavioral baselines are pure, explainable math.

## Cross-cutting decisions (locked, per dev-plan §4)

- **Detector is original code (licensing §4.7).** REACT (no license) is the
  algorithm reference only; the PREFIL + SGP4 V-pattern method is re-implemented
  from its published description, not lifted.
- **Explainability over black-box (roadmap O4).** Every detection carries the
  per-element deltas and the robust statistic that flagged it; classification is
  rule-based; baselines are interpretable cadence/Δv summaries. ML is deliberately
  deferred to Stage 7 (augment-only).
- **TLE history only (O4).** Fingerprinting uses existing `gp_history`; no new
  data dependency.

## Build sequence (Git flow — each a `feature/stage-6-*` branch off `develop`)

1. **maneuver-detection** *(this branch)* — `domain/maneuver.py` (canonical
   `Maneuver` record), `maneuver.py` (PREFIL + robust V-pattern flag on the SMA
   first-difference series, median/MAD threshold + absolute floor), migration
   `0006_maneuvers`, `repository.upsert_maneuvers`, settings knobs, and
   `pipeline.run_maneuver_loop` (registered in `main.py`). Pure-function tests.
2. **maneuver-classification** — Δv (vis-viva tangential approx, target ≤20%) +
   RIC decomposition + rule-based purpose (StationKeeping / OrbitRaise–Lower /
   Phasing / RPO). Extends the `Maneuver` record (migration `0007`).
3. **rpo-monitoring** — co-planar RPO gates (Δi/ΔRAAN/Δa) on the protected-asset
   list; `RpoMonitor` feeding the Stage-4 alert center. The watch-list stays
   config-driven (`protected_norad_ids`, the documented RPO precursor shared with
   Stage-4 screening); a CRUD watch-list table is deferred to avoid overlapping
   Stage-3's shared user-watchlist model (dev-plan §9f) — out of scope here.
4. **fingerprinting** — per-object behavioral baselines (maneuver cadence, mean
   Δv, dispersion) + deviation flags (the innovation spine; pure statistics).
5. **explainability-ui** — `api/maneuvers.py` (ABAC `MANEUVER_INTEL`) + web BFF
   routes + a React panel surfacing the Δv/RIC + V-pattern evidence and the
   behavioral-baseline/deviation views.

## Detection design (feature #10)

A natural orbit decays smoothly (drag lowers the semi-major axis along a gentle,
near-monotonic slope); a deliberate burn is an abrupt **step** in that slope —
the "V" in the SMA-vs-time plot. Working on the series of consecutive SMA
first-differences:

1. **PREFIL** — skip objects with `< maneuver_min_history_points` element sets or
   whose total SMA span never clears `maneuver_min_delta_sma_km` (no defensible
   detection possible).
2. **Robust baseline** — median + MAD (× 1.4826 ≈ σ) of the first differences.
   MAD, not stdev, so one large burn cannot inflate its own baseline and hide.
3. **Flag** — a step deviating `> maneuver_mad_k` scaled-MADs from the median
   **and** exceeding the absolute floor. The floor stops false positives against
   a noiseless feed (where any wobble is "infinitely many" MADs out).

KPIs (validated in later sub-features / Stage 8): ≥95% detection of meaningful
maneuvers; Δv estimate within ~20%; detect-to-alert < 1 collection cycle.

## Delivered (on `develop`)

All five sub-features merged via Git flow (`feature/stage-6-*` → `develop`, no-ff):

1. **maneuver-detection** — `domain/maneuver.py`, `maneuver.py`, migration `0006`,
   `run_maneuver_loop`, settings, tests.
2. **maneuver-classification** — `maneuver_analysis.py` (Δv/RIC + purpose),
   migration `0007`, detection now classifies, tests.
3. **rpo-monitoring** — `rpo.py`, `alerts.RpoMonitor`, `run_rpo_loop`,
   `fetch_catalog_elements`, tests.
4. **fingerprinting** — `fingerprint.py`, `ManeuverBaseline`, migration `0008`,
   `alerts.AnomalyMonitor`, `run_fingerprint_loop`, tests.
5. **explainability-ui** — `api/maneuvers.py` (`/maneuvers`, `/maneuvers/baselines`,
   ABAC `MANEUVER_INTEL`), web BFF routes, `lib/orbital-engine` client,
   `ManeuverPanel.tsx` (Δv/RIC + V-pattern evidence + behavioral-baseline view).

Backend: 45 pure-function tests + maneuver-API contract tests pass; ruff clean.
Web: `tsc --noEmit` and `eslint` clean. Migrations `0006`–`0008` apply over `0005`.

Deferred (consistent with the roadmap): ROK truth-data re-validation (CAS500-1 /
KOMPSAT-5) and the KPI harness land in Stage 8 system testing; ML augmentation is
Stage 7 (P2b). High-fidelity Orekit Δv is gated to later (dev-plan §3 #21).
