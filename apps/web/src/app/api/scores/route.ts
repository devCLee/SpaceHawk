// Same-origin BFF proxy for composite threat scores (mentoring #11 / S2).
//
// Backed by the engine's MANEUVER_INTEL-gated /scores endpoint. Returns
// `available: false` with an empty list (never errors) when the engine is
// offline or the caller lacks the grant, so the dashboard renders gracefully.

import { fetchScores } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: Request): Promise<Response> {
  const { searchParams } = new URL(req.url);
  const windowDays = Number(searchParams.get("window_days")) || undefined;
  const limit = Number(searchParams.get("limit")) || undefined;
  const result = await fetchScores(windowDays, limit);
  return Response.json(result, { headers: { "Cache-Control": "no-store" } });
}
