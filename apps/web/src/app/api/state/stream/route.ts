// Same-origin SSE proxy for the engine's latest-state stream.
//
// The browser's EventSource can only reach same-origin URLs and must not hold
// the internal engine address (dev-plan §4.1); the BFF forwards the engine's
// `/state/stream` straight through. One-way push of authoritative propagated
// state (§4.2/§4.5); the client interpolates between snapshots.

import { engineAuthHeaders } from "@/lib/engineSession";

const ENGINE_URL = process.env.ORBITAL_ENGINE_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${ENGINE_URL}/state/stream`, {
      headers: { Accept: "text/event-stream", ...(await engineAuthHeaders()) },
      cache: "no-store",
    });
  } catch {
    return new Response("orbital-engine unavailable", { status: 502 });
  }

  if (!upstream.ok || !upstream.body) {
    return new Response("orbital-engine state stream unavailable", {
      status: 502,
    });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
