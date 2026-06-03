# P0 Design — Zero-Trust Target Architecture

**Status:** Stage 0 design artifact (gated at the ARB). Target design, not yet built.
**Drivers:** roadmap P0 ("zero-trust target design, NIST SP 800-207 ↔ MND
accreditation"); dev-plan O7 (zero-trust is an explicit critical-path item).

## 1. Posture

Zero trust = **no implicit trust by network location**. Every request between tiers
is authenticated, authorized, and logged; the enclave's air-gap is a *containment*
boundary, **not** a substitute for internal access control. The MVP enforces this at
two seams: the **web/BFF tier** and the **Orbital Engine API** — the engine never
trusts the BFF blindly (defense-in-depth, supports segmentation).

## 2. NIST SP 800-207 tenets → SpaceHawk

| 800-207 tenet | SpaceHawk realization (MVP) |
|---|---|
| All data sources & compute are resources | Catalog, history, screening, analytics each behind the engine API; no direct DB access from the browser. |
| All comms secured regardless of location | mTLS between web↔engine and to Postgres/Redis inside the enclave; TLS terminated at nginx for clients. |
| Per-session access to resources | Short-lived sessions/tokens (Auth.js); re-authorization per request at both seams. |
| Policy from identity + attributes (dynamic) | **ABAC**: clearance × service × need-to-know (see `P0-RBAC-ABAC.md`). Default-deny. |
| Integrity & security posture monitored | Audit log (immutable), health/readiness, ingestion-health dashboards (in-enclave). |
| Auth & authz dynamic, strictly enforced | Enforced at BFF **and** engine; tokens scoped; no standing trust. |
| Collect telemetry to improve posture | In-enclave metrics/logs/traces feed the Stage-5/red-team work. |

## 3. NIST 800-207 ↔ MND accreditation mapping

The control-area mapping table (NIST 800-207 control areas ↔ MND/national
accreditation requirements) is maintained as a tracked matrix and reviewed with the
accreditation authority. **KPI:** ≥90% of NIST 800-207 control areas addressed by the
P0 gate. The matrix is the evidence artifact for that KPI; this document is its design
rationale.

## 4. Phased rollout (the key risk control)

Full zero-trust on an air-gapped enclave is high-risk if attempted at once. **Phase
it** (roadmap risk #1):

1. **Segmentation + default-deny first** — network segments per tier; deny-all
   baseline; explicit allow-lists for the few inter-tier flows.
2. **Identity & mTLS** — workload identities for web/engine/db/redis; mutual TLS on
   every internal hop.
3. **ABAC enforcement** — policy decision at both seams; default-deny authorization.
4. **Continuous verification & telemetry** — posture monitoring, audit, anomaly
   feeds; hand off to Stage-5 red-team.

## 5. Boundaries with other P0 designs

- **Operational data** entering the enclave crosses the **cross-domain / data-diode**
  path only (`P0-CROSS-DOMAIN-INGEST.md`) — the longest pole, engaged from M0.
- **Authorization model** is specified in `P0-RBAC-ABAC.md`.
- **Supply-chain** trust (mirrors, signed artifacts) is in
  `../infra/OFFLINE-SUPPLY-CHAIN.md`.

## 6. Open items for the ARB

- Confirm the accredited diode pattern to design against (drives §4 step 1).
- Confirm token lifetime / session policy with the accreditation authority.
- Approve the NIST↔MND matrix baseline and the ≥90% coverage target.
