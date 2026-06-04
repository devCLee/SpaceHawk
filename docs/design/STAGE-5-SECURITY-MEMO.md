# Stage 5 — Security: RBAC/ABAC, Audit, Hardening (implementation memo)

**Roadmap anchor:** P1 (#8) RBAC/ABAC + audit; go-live is **gated** on an
access-control pen-test. Design source: [`P0-RBAC-ABAC.md`](./P0-RBAC-ABAC.md),
[`P0-ZERO-TRUST.md`](./P0-ZERO-TRUST.md).

This memo records what Stage 5 built, the decisions taken at the two ARB-open
forks, and the residual items.

## 1. Decisions taken (the two P0-RBAC-ABAC §6 open items)

- **Auth mechanism — session cookie + `/auth/me` + guards.** The engine verifies
  credentials (bcrypt over `app_user`) and mints an **engine-signed** HS256 JWT,
  delivered as an httpOnly cookie. The web tier relays the cookie; it holds no
  signing key and never mints a token. This mirrors the reference
  AuthGuard/GuestGuard/AdminGuard convention. No external IdP — enclave-native.
- **Policy engine — embedded, in-code ABAC.** The PDP is plain Python in the
  engine (`security/policy.py`), default-deny, unit-tested directly. No external
  PDP/sidecar to add to the offline supply chain.

## 2. What was built

| Area | Where | Notes |
|---|---|---|
| ABAC PDP | `orbital_engine/security/policy.py`, `attributes.py` | Subject/Resource/Action/Context; rules: role floor, clearance dominance (U/C/S), need-to-know ⊆ grants, service scoping (tri-service + JOINT), export grant, admin IP allowlist. Default-deny. |
| Sessions | `security/{passwords,tokens,session,users}.py`, `api/auth.py`, migration `0004_users` | bcrypt; engine-signed JWT; `/auth/login \| /auth/me \| /auth/logout`; `app_user` carries the subject attributes + approval gate. |
| Enforcement | `security/enforce.py` (`requires(domain, action)`) on every catalog/state/ingest/conjunction/alert/audit route | Engine re-decides every request (zero-trust). 401 (no/invalid session) → 403 (policy deny). Alert acknowledge attributes the actor to the **token subject**, not a client field. |
| Audit | `security/audit.py`, `api/audit.py`, migration `0005_audit_log` | Every decision logged (subject, role, service, source IP, domain, action, decision, reason, path). **Append-only** via a DB trigger that rejects UPDATE/DELETE. Write is bounded (2 s) + best-effort so it cannot stall enforcement. ADMIN-only query. |
| Web auth | `apps/web` — `AuthProvider`, guards, `/signin`, `/admin/audit`, `proxy.ts`, BFF `/api/auth/*` + cookie relay | Coarse first-pass in the proxy + guards; the engine is authoritative. |
| Hardening | `next.config.mjs` security headers/CSP; `Settings.assert_secure_for_environment()`; `.env.example` (web + engine) | Production refuses a default/short JWT secret. |

## 3. Enforcement points (both seams)

1. **Web/BFF** — `proxy.ts` bounces sessionless traffic; guards shape the UI.
   First decision only.
2. **Orbital Engine** — `requires(...)` re-authenticates (validates its own JWT
   signature) and re-authorizes (PDP) on **every** request, and audits it. The
   engine never trusts the BFF; a sessionless or forged request is refused
   regardless of network position.

## 4. Test evidence

- `test_policy.py` — 18-case ABAC matrix (each gate independently).
- `test_authz.py`, `test_audit.py` — endpoint default-deny + actor attribution +
  audit write/query/immutability.
- `test_pentest.py` — the access-control battery: no / forged / expired session
  on every protected endpoint, under-privileged 403s, and the production
  secret-strength guard. (The infra-gated permit/round-trip tests run in CI with
  Postgres up.)

## 5. Residual items / follow-ups

- **Row-level classification.** Enforcement is endpoint-level; per-object
  classification/owner-service filtering (clearance applied per catalog row) is a
  follow-up. The PDP already accepts these resource attributes.
- **Fail-closed audit.** The audit write is best-effort (availability over
  completeness on a store outage). A fail-closed mode (deny if unaudited) is a
  config follow-up.
- **CSP tightening.** The CSP allows `'unsafe-eval'`/`'unsafe-inline'` for Cesium
  + Next bootstrap; nonce-based tightening is a follow-up. ONLINE Cesium-Ion mode
  must add the Ion origins to `connect-src`/`img-src`.
- **Credential provisioning.** `security/seed.py` is dev-only; enclave user
  provisioning + rotation is an operational task.
