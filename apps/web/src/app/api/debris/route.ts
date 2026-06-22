// Same-origin BFF for the tracked-debris layer (debris-viz/risk).
//
// Resilient like /api/catalog/all: lib/debris.loadDebris() prefers the live
// engine /debris, then a direct server-side CelesTrak pull, then the bundled
// snapshot — so the layer always renders. force-dynamic so live TLE orbits are
// never cached at the route.

import { loadDebris } from "@/lib/debris";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  const debris = await loadDebris();
  return Response.json(debris, { headers: { "Cache-Control": "no-store" } });
}
