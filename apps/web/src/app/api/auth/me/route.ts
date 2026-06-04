// Same-origin session-validation proxy. Forwards the session to the engine's
// /auth/me (the authoritative check) and returns the subject attributes, or the
// engine's 401. This is what the client guards poll (the reference GET_MY).

import { NextResponse } from "next/server";
import { engineAuthHeaders } from "@/lib/engineSession";

const ENGINE_URL = process.env.ORBITAL_ENGINE_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${ENGINE_URL}/auth/me`, {
      cache: "no-store",
      headers: await engineAuthHeaders(),
    });
  } catch {
    return NextResponse.json({ error: "orbital-engine unavailable" }, { status: 502 });
  }
  const data = await upstream.json().catch(() => null);
  return NextResponse.json(data, { status: upstream.status });
}
