// Same-origin BFF proxy for per-object behavioral baselines (Stage 6 #14).
// Graceful: returns `available: false` when the engine is offline or access is
// denied (mirrors /api/maneuvers).

import { fetchBaselines } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  const result = await fetchBaselines();
  return Response.json(result, { headers: { "Cache-Control": "no-store" } });
}
