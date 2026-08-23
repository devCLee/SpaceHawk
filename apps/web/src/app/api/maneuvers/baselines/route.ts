// Same-origin BFF proxy for per-object behavioral baselines (Stage 6 #14).
// Graceful: returns `available: false` when the engine is offline or access is
// denied (mirrors /api/maneuvers).

import { fetchBaselines } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: Request): Promise<Response> {
  const limit = Number(new URL(req.url).searchParams.get("limit")) || undefined;
  const result = await fetchBaselines(limit);
  return Response.json(result, { headers: { "Cache-Control": "no-store" } });
}
