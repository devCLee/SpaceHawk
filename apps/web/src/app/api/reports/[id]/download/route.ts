// Same-origin BFF proxy that streams the generated HWPX file (T9).
//
// Forwards GET /api/reports/{id}/download to the engine, passing the response
// body through with the engine's Content-Type (application/vnd.hancom.hwpx) and
// Content-Disposition (filename) intact. The engine returns 409 until the job is
// DONE, which is surfaced as-is so the panel can keep the download disabled.

import { fetchReportDownload } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const PASSTHROUGH_HEADERS = ["content-type", "content-disposition", "content-length"];

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params;
  let engineRes: Response;
  try {
    engineRes = await fetchReportDownload(id);
  } catch {
    return Response.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }

  if (!engineRes.ok) {
    const status = engineRes.status >= 500 ? 502 : engineRes.status;
    return Response.json({ error: "report not ready" }, { status });
  }

  const headers = new Headers({ "Cache-Control": "no-store" });
  for (const name of PASSTHROUGH_HEADERS) {
    const value = engineRes.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(engineRes.body, { status: 200, headers });
}
