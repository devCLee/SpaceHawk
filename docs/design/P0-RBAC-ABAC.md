# P0 Design — Access Control Model (RBAC/ABAC)

**Status:** Stage 0 design artifact (model); enforcement is built in Stage 5.
**Drivers:** roadmap feature #8 / P1 M7–M8; dev-plan Stage 5. Go-live is **gated** on
an access-control pen-test.

## 1. Decision: ABAC (attribute-based), default-deny

Plain role lists cannot express the tri-service **clearance × service × need-to-know**
matrix. The model is **ABAC**: access is a policy decision over *subject*, *resource*,
*action*, and *context* attributes, with a **default-deny** baseline. RBAC roles exist
as a convenience grouping but never widen what ABAC denies.

## 2. Attributes

| Category | Attributes |
|---|---|
| **Subject** | clearance level (U/C/S…), service (Air Force / Army / Navy), unit/role, need-to-know tags, auth strength |
| **Resource** | classification (`classification_type` U/C/S), owning service, data domain (catalog / screening / maneuver-intel / reports), object sensitivity (e.g. protected-asset watch-list) |
| **Action** | read / query / export / acknowledge-alert / administer |
| **Context** | session freshness, source tier, time, audit obligations |

## 3. Core rules (illustrative, default-deny)

- **Clearance dominance:** subject.clearance must dominate resource.classification.
- **Need-to-know:** resource need-to-know tags ⊆ subject grants, else deny.
- **Service scoping:** cross-service reads allowed only where governance grants it
  (tri-service MOU); otherwise own-service scope.
- **Export** requires an explicit export grant **and** is always audited.

## 4. Enforcement points (zero-trust)

Authorization is enforced at **both** seams (see `P0-ZERO-TRUST.md`):

1. **Web/BFF tier** (Auth.js sessions) — first decision, shapes the UI.
2. **Orbital Engine API** — re-decides every request; **never trusts the BFF**. This
   is what makes segmentation real.

Both consult the same policy; the engine is authoritative.

## 5. Auditability

Every access and mutating action writes an **immutable, queryable** audit record
(subject, resource, action, decision, context). The audit subsystem is itself a
zero-trust resource. Audit completeness is a pen-test / red-team check (Stage 5).

## 6. Open items for the ARB

- Ratify the clearance × service × need-to-know matrix with the tri-service governance
  body (depends on the signed MOU — see `P0-ARB-GATE.md`).
- ~~Confirm the policy engine approach (embedded policy vs external PDP) for the enclave.~~
  **Resolved (Stage 5): embedded in-code PDP** (`orbital_engine/security/policy.py`).
- ~~Approve the default-deny posture and the export-grant + audit requirement.~~
  **Implemented (Stage 5).**

## 7. Stage 5 implementation

This model is now built. The **auth mechanism** (left implicit here) was decided
as a **session cookie + engine-signed JWT + `/auth/me` + guard components** (no
external IdP). See [`STAGE-5-SECURITY-MEMO.md`](./STAGE-5-SECURITY-MEMO.md) for
the full enforcement map, test evidence, and residual items. Enforcement is at
both seams (web `proxy.ts`/guards + the authoritative engine `requires(...)`),
every decision is written to the append-only `audit_log`, and the access-control
pen-test battery lives in `services/orbital-engine/tests/test_pentest.py`.
