// Same-origin BFF proxy for the per-user watchlist (A2).
//
// The browser never talks to the engine directly (dev-plan §4.1 — internal
// address + auth stay server-side); the catalog-view context calls this route,
// which forwards to the engine's `/watchlist` with the session as a Bearer
// credential. The engine resolves the user from the session, so the daily report
// (which reads the watchlist per owner_username) reflects the same picks.

import { getWatchlist, addWatchlist } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  try {
    const list = await getWatchlist();
    return Response.json(list, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }
}

export async function POST(req: Request): Promise<Response> {
  let body: { object_id?: unknown };
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid request body" }, { status: 400 });
  }
  if (typeof body.object_id !== "string" || body.object_id.length === 0) {
    return Response.json({ error: "object_id required" }, { status: 400 });
  }
  try {
    const list = await addWatchlist(body.object_id);
    return Response.json(list, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }
}
