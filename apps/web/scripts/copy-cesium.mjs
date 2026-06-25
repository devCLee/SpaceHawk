// Copy Cesium's prebuilt RUNTIME assets + library JS into public/cesium so the
// globe runs without the Cesium Ion CDN (air-gap requirement, roadmap P0/§4.6).
//
// The library JS (Build/Cesium/Cesium.js, the prebuilt UMD) is copied and loaded
// at runtime via a <script> tag (CesiumWrapper), NOT bundled by webpack. Webpack
// bundling Cesium in the Next prod build crashed the renderer while evaluating
// the cesium chunk (minify-off + prebuilt-alias both failed); loading the prebuilt
// UMD as a plain script — exactly how Cesium's own CDN demos run — evaluates fine.
// The runtime asset dirs are fetched relative to CESIUM_BASE_URL ("/cesium").
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
// The prebuilt library UMD, loaded via <script src="/cesium/Cesium.js">.
const LIBRARY_FILES = ["Cesium.js"];

// Clear the dest first so any stale files from an earlier Cesium version don't
// linger; then copy the runtime dirs + the library UMD.
await rm(dest, { recursive: true, force: true });
await mkdir(dest, { recursive: true });
await Promise.all([
  ...RUNTIME_DIRS.map((dir) =>
    cp(join(src, dir), join(dest, dir), { recursive: true })
  ),
  ...LIBRARY_FILES.map((file) => cp(join(src, file), join(dest, file))),
]);
console.log(
  `[copy-cesium] ${[...RUNTIME_DIRS, ...LIBRARY_FILES].join(", ")} -> ${dest}`
);
