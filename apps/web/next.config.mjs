import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const monorepoRoot = path.join(__dirname, "../../");

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
};

export default nextConfig;
