const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // In an npm-workspaces monorepo, point file tracing at the repo root so the
  // standalone build bundles hoisted dependencies correctly.
  outputFileTracingRoot: path.join(__dirname, "../../"),
};

module.exports = nextConfig;
