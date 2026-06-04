// Same-origin BFF proxy for detected maneuvers (Stage 6 #10/#11).
//
// Backed by the engine's MANEUVER_INTEL endpoint. Returns `available: false`
// with an empty list (never errors) when the engine is offline or the caller
// lacks the grant, so the explainability panel can render a graceful state.

import { fetchManeuvers } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: Request): Promise<Response> {
  const objectId = new URL(req.url).searchParams.get("object_id") ?? undefined;
  const result = await fetchManeuvers(objectId);
  return Response.json(result, { headers: { "Cache-Control": "no-store" } });
}
