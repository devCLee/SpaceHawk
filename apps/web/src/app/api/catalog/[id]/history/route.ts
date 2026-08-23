// Same-origin BFF proxy for one object's element-set history (분석 이력 page).
// Forwards to the engine's `/catalog/{id}/history` (browser never talks to the
// engine directly, dev-plan §4.1).

import { fetchObjectHistory } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params;
  const limit = Number(new URL(req.url).searchParams.get("limit")) || undefined;
  try {
    const history = await fetchObjectHistory(id, limit);
    return Response.json(history, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }
}
