// Same-origin BFF proxy for HWPX report generation (T9).
//
// Forwards POST /api/reports to the engine's `POST /reports` (idempotent: the
// same inputs return the same job). The engine enforces ANALYST clearance — a
// 401/403 is mapped through unchanged so the chat panel can show "권한 없음".

import { createReport, type ReportRequest } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req: Request): Promise<Response> {
  let body: Partial<ReportRequest>;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid request body" }, { status: 400 });
  }
  if (body.report_type !== "daily" || typeof body.report_date !== "string") {
    return Response.json({ error: "report_type and report_date required" }, { status: 400 });
  }

  try {
    const result = await createReport({
      report_type: "daily",
      report_date: body.report_date,
      filters: body.filters,
    });
    if (!result.ok) {
      // Pass auth/validation failures through; collapse engine 5xx to 502.
      const status = result.status >= 500 ? 502 : result.status;
      return Response.json({ error: "report request rejected" }, { status });
    }
    return Response.json(result.data, {
      status: 202,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }
}
