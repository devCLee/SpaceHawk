// Same-origin BFF proxy for screened conjunctions (#9g).
//
// Backed by the Stage-4 screening service; until that engine endpoint exists,
// this returns `available: false` with an empty list so the UI can render a
// "screening pending" state without erroring.

import { fetchConjunctions } from "@/lib/orbital-engine";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: Request): Promise<Response> {
  const limit = Number(new URL(req.url).searchParams.get("limit")) || undefined;
  const result = await fetchConjunctions(limit);
  return Response.json(result, { headers: { "Cache-Control": "no-store" } });
}
