// Same-origin BFF proxy for removing one object from the per-user watchlist (A2).
//
// Forwards DELETE /api/watchlist/{id} to the engine's `DELETE /watchlist/{id}`.
// The engine returns the updated object_id list, which the context uses to
// reconcile its optimistic state.

import { removeWatchlist } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params;
  try {
    const list = await removeWatchlist(id);
    return Response.json(list, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }
}
