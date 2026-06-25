// Server-only: relay the browser's session to the engine.
//
// The engine authenticates every request itself (zero-trust); the BFF never
// mints or inspects the token, it only forwards the session cookie as a Bearer
// credential on each server-to-engine call. Imported solely from route handlers
// and other server code (uses next/headers).

import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";

/** Authorization header carrying the current session token, or empty if none. */
export async function engineAuthHeaders(): Promise<Record<string, string>> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  return token ? { Authorization: `Bearer ${token}` } : {};
}
