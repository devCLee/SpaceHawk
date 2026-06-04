// Shared auth types + role helpers (client- and server-safe — no server-only
// imports here). The web tier mirrors the engine's subject attributes; the
// engine remains authoritative (it re-decides every request). These helpers
// shape the UI only (the reference hasSuperAdminPermission pattern).

export type Role = "VIEWER" | "ANALYST" | "ADMIN";
export type Service = "AIR_FORCE" | "ARMY" | "NAVY" | "JOINT";
export type Clearance = "U" | "C" | "S";

/** The session subject as returned by the engine's /auth/me (no token, no hash). */
export interface SessionUser {
  username: string;
  role: Role;
  service: Service;
  clearance: Clearance;
  scope: string[];
  grants: string[];
}

/** Name of the engine-issued session cookie (must match the engine setting). */
export const SESSION_COOKIE = "sh_session";

/** Full administrator (mirrors the engine's ADMIN role). */
export function isAdmin(user: SessionUser | null | undefined): boolean {
  return user?.role === "ADMIN";
}

/** Core operator or above — may screen, triage, and access intelligence. */
export function isAnalyst(user: SessionUser | null | undefined): boolean {
  return user?.role === "ANALYST" || user?.role === "ADMIN";
}
