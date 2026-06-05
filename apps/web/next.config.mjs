import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const monorepoRoot = path.join(__dirname, "../../");

// Baseline security headers (Stage 5 hardening). Cesium uses WASM/eval and blob:
// workers, and Next emits inline bootstrap scripts/styles. App data fetches + SSE
// stay same-origin (through the BFF).
//
// ONLINE Cesium-Ion globe origins (the "Switch to Online" toggle). Without these,
// `connect-src 'self'` blocks the api.cesium.com asset-endpoint request at the
// browser level — emitting unsuppressable CSP-violation logs + Cesium
// RequestErrorEvents — so online mode can never load:
//   - api.cesium.com          Ion REST asset endpoints (token + tile templates)
//   - assets.ion.cesium.com   world terrain + OSM Buildings 3D tiles
//   - *.virtualearth.net      Bing world imagery tiles + metadata
// Bing imagery loads via fetch()+createImageBitmap (connect-src) on modern
// browsers and falls back to <img> (img-src), so it's listed in both.
//
// Bing tiles inherit the PAGE scheme: the dev server is http://localhost, so
// Cesium requests them over http (http://ecn.t{0-3}.tiles.virtualearth.net/...).
// A https-only source blocks those, so allow both schemes for the Bing host.
// (Ion endpoints are https-only — no http source needed.)
//
// PROD: on an https deployment the http source is unused — the page is https,
// so Cesium requests Bing tiles over https (covered by the https source). Once
// dev is also served over https, drop both http://*.virtualearth.net sources to
// keep the policy https-only.
const ionConnectSrc =
  "https://api.cesium.com https://assets.ion.cesium.com https://*.virtualearth.net http://*.virtualearth.net";
const ionImgSrc =
  "https://*.virtualearth.net http://*.virtualearth.net https://assets.ion.cesium.com";

// The online globe's imagery picker is curated to ONLY Ion/Bing-hosted basemaps
// (see CesiumComponent.tsx online branch) — Bing tiles come from *.virtualearth.net
// and Google/Sentinel/terrain are Ion-proxied via assets.ion.cesium.com, all
// already allowed below. No third-party imagery CDNs (ArcGIS/OSM/Stadia) are
// reachable, so connect-src/img-src stay locked to Ion/Bing/self (Stage 5 intact).
const contentSecurityPolicy = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:",
  "worker-src 'self' blob:",
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${ionImgSrc}`,
  "font-src 'self' data:",
  `connect-src 'self' ${ionConnectSrc}`,
  "object-src 'none'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // npm-workspaces monorepo: the lockfile lives at the repo root, so Turbopack
  // otherwise *infers* a workspace root and (Next 16 bug) mis-resolves the App
  // Router project directory to <root>/src/app -> ENOENT scandir. Pin both roots
  // to the repo root: `turbopack.root` fixes dev resolution, `outputFileTracingRoot`
  // makes the standalone build bundle hoisted dependencies.
  turbopack: {
    root: monorepoRoot,
  },
  outputFileTracingRoot: monorepoRoot,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
