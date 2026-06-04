// Same-origin login proxy. Forwards credentials to the engine's /auth/login and
// relays the engine-issued session cookie (Set-Cookie) back to the browser. The
// BFF never mints the token — the engine owns the cookie's contents and flags.

import { NextResponse } from "next/server";

const ENGINE_URL = process.env.ORBITAL_ENGINE_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    body = {};
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${ENGINE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }

  const data = await upstream.json().catch(() => ({}));
  const out = NextResponse.json(data, { status: upstream.status });
  const setCookie = upstream.headers.get("set-cookie");
  if (setCookie) out.headers.set("set-cookie", setCookie);
  return out;
}
