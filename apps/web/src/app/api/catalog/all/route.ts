// Full globe catalog as TleObjects (live engine, else bundled snapshot).
//
// The dashboard used to receive this ~15k-row catalog as an RSC prop on every
// force-dynamic request, serializing ~4MB (~1MB gz) into the document. Serving
// it from a client-fetched endpoint instead keeps it out of the document and
// stops the page from blocking first byte on the engine. The client (React
// Query) fetches it once and shares it across the globe + the country panel.
//
// force-dynamic: never cache the catalog at the route — a cached response would
// serve stale TLE orbits and break live tracking. (Live positions come from the
// SSE state stream; this list only seeds the points + identity.)
import { loadGlobeCatalog } from "@/lib/catalog";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  const entries = await loadGlobeCatalog();
  return Response.json(entries, { headers: { "Cache-Control": "no-store" } });
}
