import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // In an npm-workspaces monorepo, point file tracing at the repo root so the
  // standalone build bundles hoisted dependencies correctly.
  outputFileTracingRoot: path.join(__dirname, "../../"),
};

export default nextConfig;
