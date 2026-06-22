// Same-origin BFF for debris risk analysis (counts by level, density-by-shell,
// screened collision conjunctions).
//
// Prefers the engine /debris/risk (it adds the screening loop's real
// probability-of-collision conjunctions); when the engine is unavailable it
// computes the population summary in-process from the same debris the layer
// renders (conjunctions empty — real Pc needs the screening engine).

import { fetchDebrisRisk } from "@/lib/orbital-engine";
import { loadDebris, summarizeDebrisRisk } from "@/lib/debris";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  const engine = await fetchDebrisRisk();
  const result = engine.available
    ? engine
    : summarizeDebrisRisk(await loadDebris());
  return Response.json(result, { headers: { "Cache-Control": "no-store" } });
}
