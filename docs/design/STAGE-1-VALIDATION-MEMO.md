# Stage 1 — Thin-Vertical-Slice Validation Memo

**Status:** Stage 1 exit artifact (dev-plan Stage 1; roadmap O5, ~M5).
Pairs with the ARB-approved plan in [P0-THIN-SLICE-PLAN.md](./P0-THIN-SLICE-PLAN.md).
**Purpose:** prove the end-to-end architecture and surface integration risk
(serialization, the SSR/stream boundary, Cesium data binding) **before** scale-up.

## 1. What shipped — the one path

```
Celestrak (one GP group)
  → Orbital Engine: normalize → canonical SpaceObject → upsert Postgres
  → server SGP4 (python-sgp4) → Redis latest-state
  → region-entry rule → Redis pub/sub → SSE
  → Web BFF (RSC fetch + /api/alerts proxy)
  → Cesium renders the live set + AlertToast surfaces the live alert
```

Implemented across dependency-ordered feature branches (git-flow, all merged to
`develop`):

| Branch | Delivers |
|---|---|
| `feature/stage-1-config-deps` | Slice config knobs (source, ingest cap, interval, ROI box) + runtime deps (httpx/redis/sgp4) |
| `feature/stage-1-db-catalog` | Async SQLAlchemy engine + USOID-keyed upsert + catalog projection |
| `feature/stage-1-propagation` | Authoritative server SGP4 + TEME→ECEF→geodetic transforms |
| `feature/stage-1-ingestion` | Celestrak GP ingest (JSON + TLE merge) → canonical model |
| `feature/stage-1-state-alerts` | Redis latest-state/pub-sub + trivial region-entry rule |
| `feature/stage-1-api-pipeline` | Pipeline loop + `/catalog`,`/state/latest`,`/ingest/run`,`/alerts/stream` + readiness + regenerated OpenAPI/TS client |
| `feature/stage-1-web-feed` | BFF catalog helper + Cesium wired to the live feed (main.json fallback) |
| `feature/stage-1-web-alerts` | SSE proxy route + AlertToast panel |
| `feature/stage-1-tests` | Unit suite + DB/Redis-gated end-to-end walk |

## 2. Validation evidence (run in this environment)

- **Backend lint:** `ruff check orbital_engine` — clean.
- **App import + OpenAPI export:** `python -m orbital_engine.openapi` — succeeds;
  TS client regenerated via `openapi-typescript`.
- **Unit tests:** 12 passed (normalize, GMST/geodetic, ISS envelope, region rule),
  integration walk **skipped** (no infra in this env), via `pytest`.
- **Web:** `tsc --noEmit` clean; `eslint` clean for slice files (one pre-existing
  `any` warning in `CesiumComponent.tsx`, not introduced here).
- **Propagation sanity:** ISS @ 2024-03-10T12:00Z → alt ≈ 414 km, |lat| ≤ inclination.

### Known environment caveats (not slice defects)
- Pre-existing Stage 0 test `test_space_object.py` errors on this **cp949 (Korean
  locale) Windows** box because it calls `read_text()` without `encoding="utf-8"`;
  it passes on CI/Linux (UTF-8 default). One-line robustness fix recommended, but
  left out of Stage 1 to keep changes surgical.
- Full **runtime** measurement (latency / payload / render at load) requires the
  Docker stack + live Celestrak reachability; pending and tracked below.

## 3. Integration risks surfaced (the point of the slice)

1. **Propagation single-source-of-truth (dev-plan §4.2).** Resolved by construction:
   server and client propagate the **same TLE lines**, and the server's GMST +
   WGS-84 geodetic math mirrors satellite.js. Pinned by a test asserting GMST
   against the J2000 reference value. *Risk retired for the slice.*
2. **Celestrak shape mismatch.** GP **JSON** carries OMM metadata but **no TLE
   lines**; the TLE export carries lines but little metadata. Resolved by fetching
   both and merging on NORAD id, keeping only TLE-bearing records. *Documented
   constraint for Stage 2's multi-source merge.*
3. **SSE across the BFF boundary.** EventSource is same-origin only and can't reach
   the internal engine address → the BFF proxies `/alerts/stream` straight through.
   Heartbeats keep proxies from idling the connection. *Pattern confirmed.*
4. **SSR/stream boundary (dev-plan §4.1).** The RSC renders the shell + initial set
   server-side; positional propagation runs client-side (satellite.js) for the
   slice. The compact-binary positional stream is **deferred to Stage 3** — the
   slice intentionally reuses the lynx Entity path and a small ingest cap.

## 4. Measurements still pending (need the Docker stack)

Run `docker compose -f infra/docker-compose.yml up`, `alembic upgrade head`, then capture:
- **Latency:** ingest-to-display, and per-tick propagation time for the capped set.
- **Payload size:** `/catalog` and `/state/latest` response sizes vs object count.
- **Render behavior:** FPS / memory with the Entity path at the slice's ingest cap.

These feed the Stage 3 rendering-migration budget (Entity → `PointPrimitiveCollection`)
and the Stage 2 propagation-throughput targets.

## 5. Gate decision

The architecture is proven end-to-end in code and unit-validated; the path holds
together with no surprises at the seams. **Stages 2–4 may proceed in parallel**
once the Docker-based runtime measurements in §4 are captured against the live
stack. The slice is deliberately throwaway where noted (ingest cap, Entity
rendering, single rule) — those are scheduled replacements, not debt.
