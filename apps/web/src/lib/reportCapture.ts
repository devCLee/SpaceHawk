// Cross-tier report-image capture (R8). The engine cannot render Cesium, so the
// web supplies the report's images: per-country globe snapshots, a debris-density
// chart, and a 2D debris heatmap. This module turns the live <canvas> elements
// the dashboard already draws into the base64-PNG payload the engine's
// `POST /reports` `images` field accepts.
//
// Scope / known gap: there is no globe API to position the camera per country
// and snapshot, so the four per-country globe snapshots (NK/CN/RU/JP) are NOT
// produced here. We capture the CURRENT globe view as a single best-effort
// snapshot under "NK" (the report's lead country, §2). Real per-country capture
// is a follow-up that needs a globe imperative API (camera flyTo a country +
// render + toDataURL); see captureReportImages() docs. We deliberately do NOT
// fake four distinct snapshots from one view.

/** The report's four tracked country codes (mirrors the engine ReportCountry). */
export type ReportCountryCode = "NK" | "CN" | "RU" | "JP";

/** Base64-encoded PNGs (no data-URL prefix). Matches the engine's
 *  `images` request shape; every field is optional (best-effort capture). */
export interface ReportImagesPayload {
  country_globes?: Partial<Record<ReportCountryCode, string>>;
  debris_density?: string;
  debris_heatmap?: string;
}

/** A canvas-bearing scene we can snapshot (Cesium's `viewer.scene`). Narrowed to
 *  just what capture needs so tests can supply a stub without all of Cesium. */
export interface CaptureScene {
  canvas: HTMLCanvasElement;
  /** Cesium renders with preserveDrawingBuffer:false, so the drawing buffer is
   *  cleared after each frame; we must render once immediately before reading the
   *  canvas or toDataURL yields a blank image. */
  render: () => void;
}

const PNG_DATA_URL_PREFIX = "data:image/png;base64,";

/** Convert a canvas to a base64 PNG (no `data:` prefix), or null if the canvas
 *  can't be encoded (zero-sized, tainted, or no 2D/WebGL buffer). Pure + sync. */
export function canvasToBase64Png(canvas: HTMLCanvasElement): string | null {
  if (canvas.width === 0 || canvas.height === 0) return null;
  let dataUrl: string;
  try {
    dataUrl = canvas.toDataURL("image/png");
  } catch {
    // SecurityError on a cross-origin-tainted canvas, etc. Best-effort: skip it.
    return null;
  }
  if (!dataUrl.startsWith(PNG_DATA_URL_PREFIX)) return null;
  const b64 = dataUrl.slice(PNG_DATA_URL_PREFIX.length);
  return b64.length > 0 ? b64 : null;
}

/** Snapshot a Cesium scene's canvas to a base64 PNG. Renders one frame first so
 *  the (otherwise-cleared) drawing buffer is populated. Returns null on failure. */
export function captureScene(scene: CaptureScene): string | null {
  try {
    scene.render();
  } catch {
    return null;
  }
  return canvasToBase64Png(scene.canvas);
}

export interface CaptureSources {
  /** The live Cesium scene (viewer.scene), or null when the globe isn't mounted. */
  scene?: CaptureScene | null;
  /** The DebrisHeatmap2D canvas, or null when the heatmap overlay is closed. */
  heatmapCanvas?: HTMLCanvasElement | null;
}

/** Gather whatever report images are currently capturable into the engine
 *  payload shape, omitting anything unavailable. Returns `undefined` when nothing
 *  could be captured, so the caller posts no `images` field at all (the engine
 *  treats a no-image POST as a valid, image-less report).
 *
 *  Per-country globes: a single best-effort snapshot of the CURRENT view is
 *  stored under "NK". Producing four distinct per-country snapshots is deferred
 *  pending a globe capture API (camera-position-per-country + render + read);
 *  the globe today only exposes the viewer, with no imperative camera/snapshot
 *  surface. */
export function captureReportImages(
  sources: CaptureSources
): ReportImagesPayload | undefined {
  const payload: ReportImagesPayload = {};

  if (sources.scene) {
    const globe = captureScene(sources.scene);
    if (globe) payload.country_globes = { NK: globe };
  }

  if (sources.heatmapCanvas) {
    const heatmap = canvasToBase64Png(sources.heatmapCanvas);
    if (heatmap) payload.debris_heatmap = heatmap;
  }

  const hasAny =
    (payload.country_globes &&
      Object.keys(payload.country_globes).length > 0) ||
    payload.debris_density !== undefined ||
    payload.debris_heatmap !== undefined;
  return hasAny ? payload : undefined;
}
