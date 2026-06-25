// Same-origin logout proxy. Asks the engine to clear the session and relays the
// cookie-deletion Set-Cookie back to the browser.

import { NextResponse } from "next/server";
import { engineAuthHeaders } from "@/lib/engineSession";

const ENGINE_URL = process.env.ORBITAL_ENGINE_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${ENGINE_URL}/auth/logout`, {
      method: "POST",
      cache: "no-store",
      headers: await engineAuthHeaders(),
    });
  } catch {
    return NextResponse.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }
  const data = await upstream.json().catch(() => ({ status: "ok" }));
  const out = NextResponse.json(data, { status: upstream.status });
  const setCookie = upstream.headers.get("set-cookie");
  if (setCookie) out.headers.set("set-cookie", setCookie);
  return out;
}
