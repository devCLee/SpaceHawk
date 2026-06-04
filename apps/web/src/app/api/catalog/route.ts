// Same-origin BFF proxy for catalog queries (#9a / #9b).
//
// Forwards name/NORAD/type/country filters to the engine's `/catalog`; the
// browser never holds the internal engine address (dev-plan §4.1).

import { queryCatalog, type CatalogObject } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const p = url.searchParams;
  const limitRaw = p.get("limit");
  const offsetRaw = p.get("offset");
  try {
    const rows: CatalogObject[] = await queryCatalog({
      q: p.get("q") ?? undefined,
      object_type: p.get("object_type") ?? undefined,
      country_code: p.get("country_code") ?? undefined,
      limit: limitRaw ? Number(limitRaw) : undefined,
      offset: offsetRaw ? Number(offsetRaw) : undefined,
    });
    return Response.json(rows, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json(
      { error: "orbital-engine unavailable" },
      { status: 502 }
    );
  }
}
