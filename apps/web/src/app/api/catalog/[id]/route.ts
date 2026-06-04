// Same-origin BFF proxy for one object's catalog detail.
//
// The browser never talks to the engine directly (dev-plan §4.1 — internal
// address + queries stay server-side); the sidebar fetches this route, which
// forwards to the engine's `/catalog/{id}`.

import { fetchObjectDetail } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params;
  try {
    const detail = await fetchObjectDetail(id);
    if (detail === null) {
      return Response.json({ error: "object not found" }, { status: 404 });
    }
    return Response.json(detail, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }
}
