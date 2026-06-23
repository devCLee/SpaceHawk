// Cross-tier report-image capture (R8). The engine cannot render Cesium, so the
// web supplies the report's images: per-country globe snapshots, a debris-density
// chart, and a 2D debris heatmap. This module turns the live <canvas> elements
// the dashboard already draws into the base64-PNG payload the engine's
// `POST /reports` `images` field accepts.
//
// Per-country globes: the camera is positioned over each of the four report
// countries (NK/CN/RU/JP) in turn and the framed view is snapshotted, producing
// four distinct images. The imperative position-then-capture is driven by
// GlobeControls (which owns the live Cesium viewer/camera); the pure pieces — the
// per-country camera targets, the render-then-wait-then-encode capture loop — live
// here so they can be unit-tested without Cesium.

/** The report's four tracked country codes (mirrors the engine ReportCountry). */
export type ReportCountryCode = "NK" | "CN" | "RU" | "JP";

/** All four report countries, in the capture/report order (NK leads, §2). */
export const REPORT_COUNTRY_CODES: readonly ReportCountryCode[] = [
  "NK",
  "CN",
  "RU",
  "JP",
] as const;

/** Where to point the camera to frame a country: its centroid lon/lat plus the
 *  camera altitude above it. A straight-down (nadir) view over the centroid is
 *  deterministic and frames the whole country without per-country pitch tuning. */
export interface CameraTarget {
  /** Centroid longitude, degrees east. */
  lon: number;
  /** Centroid latitude, degrees north. */
  lat: number;
  /** Camera height above the centroid, metres. Larger = wider area framed. */
  heightMeters: number;
}

// Per-country camera targets. Centroids are approximate national centroids;
// heights are hand-tuned so each country (and enough surrounding context) fills
// the frame — small/elongated NK gets a closer view than continental CN/RU.
const COUNTRY_CAMERA_TARGETS: Record<ReportCountryCode, CameraTarget> = {
  // North Korea — small + elongated, so the closest view.
  NK: { lon: 127.5, lat: 40.0, heightMeters: 2_000_000 },
  // China — continental; pull well back to fit it.
  CN: { lon: 103.8, lat: 35.0, heightMeters: 9_000_000 },
  // Russia — spans many time zones; centroid sits in Siberia, farthest back.
  RU: { lon: 96.0, lat: 61.5, heightMeters: 12_000_000 },
  // Japan — archipelago; a medium view covers the island chain.
  JP: { lon: 138.0, lat: 37.5, heightMeters: 3_500_000 },
};

/** The camera target (centroid lon/lat + height) for a report country. */
export function cameraTargetForCountry(country: ReportCountryCode): CameraTarget {
  return COUNTRY_CAMERA_TARGETS[country];
}

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

/** The minimal globe surface the per-country capture drives. Narrowed (vs. the
 *  full Cesium Viewer) so tests can supply a stub: position the camera, render a
 *  frame, ask whether imagery/terrain tiles have finished loading, and snapshot.
 *  Implemented over a real Cesium viewer in GlobeControls. */
export interface CountryCaptureScene {
  /** Position the camera (instant `setView`) to frame the given country. */
  positionCamera: (target: CameraTarget) => void;
  /** Render one frame (Cesium clears its drawing buffer between frames). */
  render: () => void;
  /** True once the globe's imagery/terrain tiles for the current view are loaded. */
  tilesLoaded: () => boolean;
  /** The scene canvas to encode. */
  canvas: HTMLCanvasElement;
}

/** Bounded wait for Cesium to finish streaming tiles for the current camera view.
 *  Cesium loads imagery/terrain asynchronously, so a snapshot taken immediately
 *  after `setView` shows a half-loaded (blank/blurry) globe. We poll
 *  `scene.globe.tilesLoaded`, rendering a frame each poll to drive the tile
 *  requests forward, and give up after `timeoutMs` so capture can never hang —
 *  a slightly-unsettled snapshot is preferable to blocking the report submit. */
export interface TilesWaitOptions {
  /** Hard cap on the wait before we snapshot whatever is there. */
  timeoutMs?: number;
  /** Delay between tilesLoaded polls. */
  pollMs?: number;
  /** Injectable timer (tests pass a synchronous resolver). */
  sleep?: (ms: number) => Promise<void>;
}

const DEFAULT_TILES_WAIT: Required<Omit<TilesWaitOptions, "sleep">> = {
  timeoutMs: 4000,
  pollMs: 100,
};

const realSleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

/** Render frames and poll until tiles are loaded or the timeout elapses. */
export async function waitForTilesLoaded(
  scene: Pick<CountryCaptureScene, "render" | "tilesLoaded">,
  options: TilesWaitOptions = {}
): Promise<void> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TILES_WAIT.timeoutMs;
  const pollMs = options.pollMs ?? DEFAULT_TILES_WAIT.pollMs;
  const sleep = options.sleep ?? realSleep;
  const deadline = Date.now() + timeoutMs;
  // Render once up front so the new view starts requesting its tiles.
  scene.render();
  while (!scene.tilesLoaded()) {
    if (Date.now() >= deadline) return; // give up — capture whatever is rendered
    await sleep(pollMs);
    scene.render();
  }
}

/** Position the camera over a country, wait for its tiles to settle (bounded),
 *  then snapshot the framed view to a base64 PNG. Returns null on any failure
 *  (best-effort). Does NOT save/restore the camera — the caller owns that so it
 *  can restore once after a batch of captures. */
export async function captureCountryScene(
  scene: CountryCaptureScene,
  country: ReportCountryCode,
  options: TilesWaitOptions = {}
): Promise<string | null> {
  try {
    scene.positionCamera(cameraTargetForCountry(country));
    await waitForTilesLoaded(scene, options);
    scene.render(); // final frame immediately before reading the cleared buffer
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
 *  Per-country globes: this helper only snapshots the CURRENT view (filed under
 *  "NK"). Four distinct per-country snapshots are produced separately by
 *  GlobeControls.captureAllCountryGlobes() (camera-position-per-country + tile
 *  wait + read); see captureCountryScene above. */
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
