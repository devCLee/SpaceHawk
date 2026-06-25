# License Decision Record

**Status:** Stage 0 deliverable (dev-plan §4.7 — "resolve before coding, the
highest-priority risk"). Records the licensing posture; **confirm at the ARB.**

## 1. This repository

SpaceHawk ships an explicit **`LICENSE` (GNU AGPL-3.0)** at the repo root. This is a
deliberate grant for the SpaceHawk codebase itself and resolves the dev-plan's
original "lynx has no license" concern *for this repo*.

> **ARB item — AGPL network-use clause.** AGPL-3.0's §13 attaches obligations to
> software made available **over a network** (which a served dashboard is). For a
> defense delivery this is a real consideration. Confirm at the ARB that AGPL-3.0 is
> the intended outbound license for the delivered system, or relicense before wider
> distribution. (Internal/enclave-only deployment to the operating organization may
> not trigger distribution obligations — confirm with counsel.)

## 2. Reuse policy by upstream source

| Source | License | Decision | Rationale |
|---|---|---|---|
| **Cesium** | Apache-2.0 | **Reuse** | Permissive; already a dependency. Self-host assets (no Ion). |
| **satellite.js** | MIT | **Reuse** | Permissive; client-side SGP4 for display. |
| **project-lynx2** | MIT | **Reuse with attribution** | Same stack; donates the per-satellite info sidebar + filter (#9h). Keep MIT attribution. |
| **REACT** | none (all-rights-reserved) | **Re-implement from published methods** | Want the algorithms (SGP4 V-pattern maneuver detection, station-keeping); do **not** lift code. License from author *or* clean-room. |
| **Sovereign_Watch** | AGPL-3.0 | **Reference only** | Architecture/pattern reference; build the FastAPI engine as original code. |
| **keeptrack.space** | AGPL-3.0 | **Reference only** | Functional/UX reference for the catalog-interaction tools; build fresh. |

## 3. Operating rules

- **No code is copied** from no-license (REACT) or from AGPL upstreams
  (Sovereign_Watch, keeptrack) into the delivered codebase — they are **references**.
  Original, independently-written implementations only.
- **Permissive pieces** (Cesium Apache-2.0, satellite.js MIT, project-lynx2 MIT) may
  live in the codebase, with attribution where required.
- **Reference datasets** (sensor sites, country/operator, constellation membership)
  that keeptrack ships under AGPL must be **sourced/curated independently**.
- Any new dependency is recorded in `docs/DECISIONS.md` with its license and purpose.

## 4. ARB sign-off checklist

- [ ] AGPL-3.0 confirmed (or relicensed) as the outbound license for the delivery.
- [ ] REACT path chosen (author license vs clean-room) and recorded.
- [ ] "Reference-only" treatment of AGPL upstreams acknowledged in writing.
- [ ] project-lynx2 MIT attribution plan agreed.
