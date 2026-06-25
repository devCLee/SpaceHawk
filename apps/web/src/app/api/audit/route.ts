// Same-origin proxy for the engine's ADMIN-only audit log. Forwards the session,
// the pagination window (limit/offset), the substring filters (subject/path) and
// the multi-select OR filters (decision/role/domain/action) — the latter as
// repeated query params. The engine enforces ADMIN access (and audits the read).
// Returns the engine's status verbatim (401/403 surface to the UI).

import { engineAuthHeaders } from "@/lib/engineSession";

const ENGINE_URL = process.env.ORBITAL_ENGINE_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: Request): Promise<Response> {
  const incoming = new URL(req.url);
  const params = new URLSearchParams();
  for (const key of ["subject", "path", "source_ip", "ts_from", "ts_to", "limit", "offset"]) {
    const v = incoming.searchParams.get(key);
    if (v) params.set(key, v);
  }
  for (const key of ["decision", "role", "domain", "action"]) {
    for (const v of incoming.searchParams.getAll(key)) {
      if (v) params.append(key, v);
    }
  }
  try {
    const res = await fetch(`${ENGINE_URL}/audit?${params.toString()}`, {
      cache: "no-store",
      headers: await engineAuthHeaders(),
    });
    const data = await res.json().catch(() => null);
    return Response.json(data, { status: res.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }
}
