# P0 Architecture Review Board (ARB) Gate

**Status:** Stage 0 exit gate. This is the checklist the ARB signs to authorize
Phase 1. It indexes the P0 design pack and the foundation actually built in Stage 0.

## 1. P0 KPIs (roadmap)

| KPI | Target | Evidence |
|---|---|---|
| NIST 800-207 control areas addressed | **≥90%** | NIST↔MND matrix (`P0-ZERO-TRUST.md` §3) |
| Tri-service MOU signed | **by M3** | governance / data-governance charter |
| Interfaces specified to CCSDS/STANAG | **100%** | canonical model + interface specs (`../data-model/CANONICAL-OBJECT-MODEL.md`) |

## 2. Design pack (gated artifacts)

| Artifact | Document |
|---|---|
| Zero-trust target design (NIST 800-207 ↔ MND) | `P0-ZERO-TRUST.md` |
| Cross-domain / data-diode ingest (accredited-in-principle) | `P0-CROSS-DOMAIN-INGEST.md` |
| RBAC/ABAC access-control model | `P0-RBAC-ABAC.md` |
| License decision record | `LICENSE-DECISION-RECORD.md` |
| Thin-vertical-slice plan (O5) | `P0-THIN-SLICE-PLAN.md` |
| Canonical object model (CCSDS freeze) | `../data-model/CANONICAL-OBJECT-MODEL.md` |
| Offline supply-chain strategy | `../infra/OFFLINE-SUPPLY-CHAIN.md` |

## 3. Foundation built in Stage 0 (engineering deliverables)

| Deliverable | Where | Verified |
|---|---|---|
| Polyglot monorepo (apps/web, services/orbital-engine, packages/shared-types, infra) + CODEOWNERS | repo root | build/lint/typecheck green |
| Canonical model: JSON Schema + Pydantic + SQL DDL + drift test | `packages/…`, `services/…`, `infra/db/ddl` | 268-record parse + schema-conformance test |
| FastAPI skeleton (health/OpenAPI/settings/structured logging) + generated TS client | `services/orbital-engine`, `packages/shared-types` | 10 pytest checks; client typechecks |
| Local stack (Postgres+PostGIS+TimescaleDB, Redis, both apps) + Alembic migration | `infra/`, `services/…/migrations` | migration applied+rolled back on real Postgres 16 + PostGIS 3.4 |
| CI (both tiers, contract-drift, compose validate) | `.github/workflows/ci.yml` | pipeline defined; local dry-run green |

## 4. Top P0 risks & mitigations (carried into Phase 1)

1. **Zero-trust on an air-gapped enclave** → phase it (segmentation + default-deny
   first). `P0-ZERO-TRUST.md` §4.
2. **Tri-service data-model divergence** → freeze a single CCSDS canonical model
   (done). `../data-model/CANONICAL-OBJECT-MODEL.md`.
3. **Cross-domain accreditation slips** → engage at M0; design to an accredited diode
   pattern. `P0-CROSS-DOMAIN-INGEST.md`.

## 5. ARB sign-off

- [ ] KPIs (§1) on track; matrix/MOU/interface evidence reviewed.
- [ ] Zero-trust phased-rollout approved; accredited diode pattern chosen.
- [ ] Canonical model **frozen** (change-control per the model doc §6).
- [ ] ABAC default-deny model ratified (matrix pending MOU).
- [ ] License posture confirmed (AGPL outbound decision per the record).
- [ ] Thin-vertical-slice plan approved to start at Phase-1 open.

**Decision:** ☐ Proceed to Phase 1  ☐ Proceed with conditions  ☐ Hold
