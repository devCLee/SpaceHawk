// Same-origin BFF proxy for the durable alert log (alert center, Stage 4).
//
// Distinct from the sibling `/api/alerts` SSE stream: this is the queryable,
// triageable history the alert center lists. Forwards to the engine's `/alerts`
// (browser never talks to the engine directly, dev-plan §4.1).

import { fetchAlerts } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: Request): Promise<Response> {
  const status = new URL(req.url).searchParams.get("status") ?? undefined;
  try {
    const alerts = await fetchAlerts(status);
    return Response.json(alerts, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }
}
