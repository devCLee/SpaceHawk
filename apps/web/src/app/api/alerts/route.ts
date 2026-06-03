// Same-origin SSE proxy for the engine's alert stream.
//
// The browser's EventSource can only reach same-origin URLs (and can't set the
// internal engine address or auth), so the BFF proxies the engine's
// `/alerts/stream` through to the client, passing the raw event stream straight
// through. One-way push only (dev-plan §4.5).

const ENGINE_URL = process.env.ORBITAL_ENGINE_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${ENGINE_URL}/alerts/stream`, {
      headers: { Accept: "text/event-stream" },
      cache: "no-store",
    });
  } catch {
    return new Response("orbital-engine unavailable", { status: 502 });
  }

  if (!upstream.ok || !upstream.body) {
    return new Response("orbital-engine alert stream unavailable", { status: 502 });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
