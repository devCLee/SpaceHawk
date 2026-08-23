// Same-origin BFF proxy for the threat-level history (trend chart on 위협 점수).
//
// Backed by the engine's MANEUVER_INTEL-gated /scores/history endpoint.
// Returns `available: false` with empty points (never errors) when the engine
// is offline or the caller lacks the grant.

import { fetchScoresHistory } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: Request): Promise<Response> {
  const { searchParams } = new URL(req.url);
  const days = Number(searchParams.get("days")) || undefined;
  const windowDays = Number(searchParams.get("window_days")) || undefined;
  const result = await fetchScoresHistory(days, windowDays);
  return Response.json(result, { headers: { "Cache-Control": "no-store" } });
}
