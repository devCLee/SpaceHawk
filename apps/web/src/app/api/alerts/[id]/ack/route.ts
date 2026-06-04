// Same-origin BFF proxy for alert acknowledge/dismiss (triage, Stage 4).
//
// Forwards a POST to the engine's `/alerts/{id}/ack`. The body selects the new
// triage status (ACK or DISMISSED) and an optional actor.

import { acknowledgeAlert } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params;
  let body: { status?: "ACK" | "DISMISSED"; acknowledged_by?: string };
  try {
    body = await req.json();
  } catch {
    body = {};
  }
  try {
    const updated = await acknowledgeAlert(id, {
      status: body.status === "DISMISSED" ? "DISMISSED" : "ACK",
      acknowledged_by: body.acknowledged_by,
    });
    if (updated === null) {
      return Response.json({ error: "alert not found" }, { status: 404 });
    }
    return Response.json(updated, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }
}
