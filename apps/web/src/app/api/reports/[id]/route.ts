// Same-origin BFF proxy for one report job's status (T9).
//
// Forwards GET /api/reports/{id} to the engine's `GET /reports/{job_id}`. The
// chat panel polls this until status is DONE or FAILED.

import { fetchReportJob } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params;
  try {
    const result = await fetchReportJob(id);
    if (!result.ok) {
      const status = result.status >= 500 ? 502 : result.status;
      return Response.json({ error: "report status unavailable" }, { status });
    }
    return Response.json(result.data, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }
}
