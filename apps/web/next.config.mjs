import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const monorepoRoot = path.join(__dirname, "../../");

// Baseline security headers (Stage 5 hardening). The CSP is scoped to what the
// offline globe needs: Cesium uses WASM/eval and blob: workers, and Next emits
// inline bootstrap scripts/styles. `connect-src 'self'` keeps all data fetches
// and SSE same-origin (through the BFF). ONLINE Cesium-Ion mode would need the
// Ion + imagery origins added to connect-src/img-src.
const contentSecurityPolicy = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:",
  "worker-src 'self' blob:",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
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
