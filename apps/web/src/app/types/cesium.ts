export type CesiumType = typeof import('cesium');

// Cesium is loaded at runtime as a prebuilt UMD via <script src="/cesium/Cesium.js">
// (see CesiumWrapper), which attaches the namespace to `window.Cesium`. It is NOT
// webpack-bundled (that crashed the prod renderer while evaluating the chunk).
declare global {
  interface Window {
    Cesium?: CesiumType;
  }
}
