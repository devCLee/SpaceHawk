// Copy Cesium's prebuilt RUNTIME assets into public/cesium so the globe runs
// without the Cesium Ion CDN (air-gap requirement, roadmap P0/§4.6).
//
// Only the asset dirs Cesium fetches at run time via CESIUM_BASE_URL are copied
// (CesiumComponent sets `window.CESIUM_BASE_URL = "/cesium"`). The library JS in
// Build/Cesium — Cesium.js / index.js / index.cjs, ~15MB combined — is NOT
// copied: the app loads Cesium from the webpack bundle (`import "cesium"`), which
// resolves from node_modules, never from public/. Copying it just shipped ~15MB
// of dead static files (served, cached, and built into the standalone image for
// nothing). public/cesium drops from ~23MB to ~8MB.
//
// Resolves Cesium via Node module resolution rather than a fixed
// `node_modules/cesium` path, so it works whether the dependency is hoisted to
// the workspace root (npm workspaces) or installed locally.
import { cp, rm, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const cesiumRoot = dirname(require.resolve("cesium/package.json"));
const src = join(cesiumRoot, "Build", "Cesium");
const dest = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "cesium");

// The four dirs Cesium requests relative to CESIUM_BASE_URL: web workers, static
// assets (textures, IAU data — buildModuleUrl("Assets/...")), widget CSS/images,
// and bundled third-party worker deps (draco, etc.).
const RUNTIME_DIRS = ["Workers", "Assets", "Widgets", "ThirdParty"];

// Clear the dest first so a previous full copy's library JS (and any stale files
// from an earlier Cesium version) don't linger; then copy only the runtime dirs.
await rm(dest, { recursive: true, force: true });
await mkdir(dest, { recursive: true });
await Promise.all(
  RUNTIME_DIRS.map((dir) =>
    cp(join(src, dir), join(dest, dir), { recursive: true })
  )
);
console.log(`[copy-cesium] ${RUNTIME_DIRS.join(", ")} -> ${dest}`);
