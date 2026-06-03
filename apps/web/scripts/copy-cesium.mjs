// Copy Cesium's prebuilt static assets into public/cesium so the globe runs
// without the Cesium Ion CDN (air-gap requirement, roadmap P0/§4.6).
//
// Resolves Cesium via Node module resolution rather than a fixed
// `node_modules/cesium` path, so it works whether the dependency is hoisted
// to the workspace root (npm workspaces) or installed locally.
import { cp } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const cesiumRoot = dirname(require.resolve("cesium/package.json"));
const src = join(cesiumRoot, "Build", "Cesium");
const dest = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "cesium");

await cp(src, dest, { recursive: true });
console.log(`[copy-cesium] ${src} -> ${dest}`);
