// Same-origin BFF proxy for one object's catalog detail.
//
// The browser never talks to the engine directly (dev-plan §4.1 — internal
// address + queries stay server-side); the sidebar fetches this route, which
// forwards to the engine's `/catalog/{id}`.

import { fetchObjectDetail } from "@/lib/orbital-engine";
import { findSnapshotDetail } from "@/lib/snapshotCatalog";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params;

  // The engine DB is authoritative. But the globe renders the bundled snapshot
  // when the engine catalog is unavailable/sparse (main/page.tsx), so a click can
  // arrive for an object the engine doesn't have — fall back to snapshot-derived
  // detail so the sidebar still populates, mirroring the globe's own fallback.
  let detail = null;
  let engineUnavailable = false;
  try {
    detail = await fetchObjectDetail(id);
  } catch {
    engineUnavailable = true;
  }

  if (detail === null) {
    detail = findSnapshotDetail(id);
  }

  if (detail !== null) {
    return Response.json(detail, {
      headers: { "Cache-Control": "no-store" },
    });
  }

  return engineUnavailable
    ? Response.json({ error: "orbital-engine unavailable" }, { status: 502 })
    : Response.json({ error: "object not found" }, { status: 404 });
}
