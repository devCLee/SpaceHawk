// Coarse, first-pass gate (the engine re-decides authoritatively). Requests with
// no session cookie are bounced: API calls get a 401, page loads get redirected
// to /signin — so unauthenticated users never even load the dashboard bundle.
// Signature validation and ABAC happen at the engine; this only checks presence.
//
// Next 16 "proxy" convention (the renamed middleware).

import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // The auth endpoints and the sign-in page must stay reachable while signed out.
  if (pathname.startsWith("/api/auth") || pathname === "/signin") {
    return NextResponse.next();
  }

  if (req.cookies.has(SESSION_COOKIE)) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "authentication required" }, { status: 401 });
  }
  const url = req.nextUrl.clone();
  url.pathname = "/signin";
  return NextResponse.redirect(url);
}

// Run on everything except Next internals, the favicon, and the self-hosted
// Cesium assets (served from /cesium for the air-gapped globe).
export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|cesium).*)"],
};
