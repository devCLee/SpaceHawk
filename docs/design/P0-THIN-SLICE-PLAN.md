# P0 Design — Thin-Vertical-Slice Plan (for ARB approval)

**Status:** Stage 0 deliverable — the ARB approves this plan so the spike can begin
the moment Phase 1 opens (roadmap O5; dev-plan Stage 1, ~M5).

## 1. Goal

Prove the whole architecture end-to-end **before** scale-up, surfacing integration
risk (serialization, the SSR/stream boundary, Cesium data binding) early. Deliberately
throwaway-quality where needed — the point is de-risking, not polish.

## 2. The one path

```
Celestrak (one group, e.g. active.json)
  → Orbital Engine: normalize to canonical model → upsert Postgres
  → server SGP4 (current state for the set) → Redis "latest state"
  → SSE channel emits one trivial rule-based alert (e.g. object enters a region)
  → Web: Cesium renders the set (replacing main.json); subscribes to the SSE alert
```

## 3. Scope (in / out)

- **In:** one source, one canonical upsert, one server-propagation endpoint, one Redis
  latest-state, one SSE alert, Cesium wired to the live feed + a toast/alert panel,
  one integration test that walks the whole path, deploy to the dev enclave.
- **Out:** multi-source ingestion, scale rendering (10k+), screening, analytics, full
  RBAC — all later stages.

## 4. Why it's already de-risked

Stage 0 has landed the substrate the slice needs: the canonical model + JSON Schema,
the FastAPI skeleton + typed TS client, the Postgres/Redis compose stack, and the
migration. The slice is mostly *wiring*, which is exactly the integration risk we want
to expose.

## 5. Exit artifact

A demoable spike **plus an architecture-validation memo** (latency, payload size,
render behavior) that informs Stages 2–4. Gates confident parallel work.
