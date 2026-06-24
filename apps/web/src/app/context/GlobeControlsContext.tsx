"use client";

// Shared state for the unified top-right globe controls. The Cesium globe lives
// deep in the dashboard tree, but its controls (online/offline imagery, the
// scene-mode picker, the imagery/terrain picker) now live in the global Header.
// This context bridges the two: CesiumComponent registers its viewer here and
// reads `mode`; the Header drives scene-mode + imagery and toggles `mode`.
//
// It is inert off the dashboard — with no viewer registered, `active` is false
// and the Header simply omits the globe-view group.

import React from "react";
// Type-only: this context is loaded app-wide (via providers), so it must NOT
// pull cesium into the always-loaded graph. The cesium runtime namespace is
// handed in at registerViewer time by CesiumComponent (the single ssr:false
// boundary that owns cesium), keeping cesium in exactly one chunk.
import type { Viewer } from "cesium";
import {
  captureScene,
  captureCountryScene,
  REPORT_COUNTRY_CODES,
  type CameraTarget,
  type CountryCaptureScene,
  type ReportCountryCode,
} from "@/lib/reportCapture";

/** Online = Cesium Ion imagery/terrain; offline = bundled Natural Earth II. */
export type GlobeMode = "offline" | "online";
/** Cesium's three scene projections (SceneModePicker parity). */
export type SceneMode = "3D" | "2D" | "Columbus";

/** Options for waiting on the Cesium viewer to register before a globe capture.
 *  The report chat can fire right after a page load, before CesiumComponent has
 *  finished mounting and calling registerViewer; without this wait the capture
 *  returns `{}` and the report silently ships with no globes. Injectable for
 *  tests (sleep can register a late viewer to exercise the wait path). */
export interface CaptureReadyOptions {
  /** Max time to wait for a viewer to register before giving up (ms). */
  readyTimeoutMs?: number;
  /** Delay between readiness polls (ms). */
  pollMs?: number;
  /** Injectable timer (tests pass a synchronous / viewer-registering resolver). */
  sleep?: (ms: number) => Promise<void>;
}

const DEFAULT_VIEWER_WAIT = { readyTimeoutMs: 8000, pollMs: 150 } as const;

const realSleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

/** Resolve once a non-destroyed viewer is registered, or null after the timeout.
 *  Polls the live ref so a viewer that registers mid-wait (Cesium still mounting
 *  when the report is submitted) is picked up rather than missed. */
async function awaitRegisteredViewer(
  ref: { current: Viewer | null },
  options: CaptureReadyOptions = {}
): Promise<Viewer | null> {
  const timeoutMs = options.readyTimeoutMs ?? DEFAULT_VIEWER_WAIT.readyTimeoutMs;
  const pollMs = options.pollMs ?? DEFAULT_VIEWER_WAIT.pollMs;
  const sleep = options.sleep ?? realSleep;
  const deadline = Date.now() + timeoutMs;
  let viewer = ref.current;
  while ((!viewer || viewer.isDestroyed()) && Date.now() < deadline) {
    await sleep(pollMs);
    viewer = ref.current;
  }
  return viewer && !viewer.isDestroyed() ? viewer : null;
}

interface GlobeControlsValue {
  mode: GlobeMode;
  setMode: (mode: GlobeMode) => void;
  sceneMode: SceneMode;
  setSceneMode: (mode: SceneMode) => void;
  imageryOpen: boolean;
  toggleImagery: () => void;
  /** The curated BaseLayerPicker only exists in online mode. */
  imageryAvailable: boolean;
  /** True while a Cesium viewer is mounted (i.e. the globe dashboard is shown). */
  active: boolean;
  /** Left analyst rail (ControlRail) open/closed; Header owns the toggle. */
  railOpen: boolean;
  toggleRail: () => void;
  /** Region-of-interest overlay box on the globe; Header owns the toggle. */
  roiVisible: boolean;
  toggleRoi: () => void;
  /** CesiumComponent registers its viewer on build and `null` on teardown. It
   *  also passes the cesium namespace so this app-wide context can drive the
   *  camera (e.g. globe capture) without statically importing cesium itself. */
  registerViewer: (viewer: Viewer | null, cesium?: typeof import("cesium")) => void;
  /** Snapshot the current globe view as a base64 PNG (no data-URL prefix), or
   *  null when no viewer is mounted / the canvas can't be encoded. Used by the
   *  report capture (R8). Renders one frame first (Cesium clears its buffer). */
  captureGlobe: () => string | null;
  /** Position the camera over a report country (NK/CN/RU/JP), wait for its tiles
   *  to settle, snapshot the framed view to a base64 PNG, then RESTORE the user's
   *  prior camera. Returns null when no viewer is mounted or capture fails
   *  (best-effort). Async because Cesium streams tiles. */
  captureCountryGlobe: (country: ReportCountryCode) => Promise<string | null>;
  /** Capture all four report countries in order, restoring the camera once at the
   *  end. Returns a map of the countries that captured successfully (failures /
   *  nulls are skipped). Waits (bounded) for the Cesium viewer to register first,
   *  so a report submitted right after page load still captures globes; returns
   *  empty only when no viewer registers within the timeout. */
  captureAllCountryGlobes: (
    options?: CaptureReadyOptions
  ) => Promise<Partial<Record<ReportCountryCode, string>>>;
}

const GlobeControlsContext = React.createContext<GlobeControlsValue | null>(
  null
);

// Cesium's default scene morph is a 2.0s animated transition (see
// Scene.morphTo3D `[duration = 2.0]`), which is what the native SceneModePicker
// used. Match it for user-initiated switches so the 2D/3D/Columbus morph stays
// smooth.
const SCENE_MORPH_SEC = 2.0;

// Cesium's Viewer type defs omit `baseLayerPicker.viewModel.dropDownVisible`
// from the public surface even though it exists at runtime; reach it through a
// narrow shape rather than `any`.
type ViewerWithPicker = Viewer & {
  baseLayerPicker?: {
    viewModel: { dropDownVisible: boolean };
    // BaseLayerPicker's private capture-phase document close handler.
    _closeDropDown?: (e: Event) => void;
  };
};

// Flip Cesium's BaseLayerPicker dropdown and report the new state, or null when
// there is no picker (offline mode). Kept at module scope so mutating the
// viewModel isn't flagged as mutating a value reachable from the viewer ref.
function toggleViewerImagery(viewer: ViewerWithPicker | null): boolean | null {
  const picker = viewer?.baseLayerPicker;
  if (!picker) return null;
  const next = !picker.viewModel.dropDownVisible;
  picker.viewModel.dropDownVisible = next;
  return next;
}

export function GlobeControlsProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  // Default offline: the app ships a strict CSP that blocks Cesium Ion, so the
  // globe boots on the bundled offline imagery and the user opts into online.
  const [mode, setMode] = React.useState<GlobeMode>("offline");
  const [sceneMode, setSceneModeState] = React.useState<SceneMode>("3D");
  const [imageryOpen, setImageryOpen] = React.useState(false);
  const [imageryAvailable, setImageryAvailable] = React.useState(false);
  const [active, setActive] = React.useState(false);
  // Rail starts open (current default layout); the Header toggle hides/shows it.
  const [railOpen, setRailOpen] = React.useState(true);
  const toggleRail = React.useCallback(() => setRailOpen((v) => !v), []);
  // ROI box starts hidden; the Header toggle reveals the region overlay.
  const [roiVisible, setRoiVisible] = React.useState(false);
  const toggleRoi = React.useCallback(() => setRoiVisible((v) => !v), []);

  const viewerRef = React.useRef<Viewer | null>(null);
  // The cesium namespace, handed in by CesiumComponent at register time. Lets
  // globe-capture build Cartesian3 destinations without this app-wide context
  // statically importing cesium (which would re-create the cross-boundary chunk).
  const cesiumRef = React.useRef<typeof import("cesium") | null>(null);
  // Mirror sceneMode in a ref so registerViewer can re-apply the latest choice
  // after a viewer rebuild without re-creating the callback on every change.
  const sceneModeRef = React.useRef<SceneMode>(sceneMode);

  // `durationSec` is the morph animation length: SCENE_MORPH_SEC for a user
  // switch (smooth), 0 only when restoring the projection on a freshly rebuilt
  // viewer (no animation wanted there).
  const applyScene = React.useCallback(
    (viewer: Viewer, next: SceneMode, durationSec: number) => {
      if (viewer.isDestroyed()) return;
      try {
        if (next === "3D") viewer.scene.morphTo3D(durationSec);
        else if (next === "2D") viewer.scene.morphTo2D(durationSec);
        else viewer.scene.morphToColumbusView(durationSec);
      } catch {
        /* scene not ready yet — the next registerViewer/setSceneMode re-applies */
      }
    },
    []
  );

  const setSceneMode = React.useCallback(
    (next: SceneMode) => {
      sceneModeRef.current = next;
      setSceneModeState(next);
      const viewer = viewerRef.current;
      if (viewer) applyScene(viewer, next, SCENE_MORPH_SEC);
    },
    [applyScene]
  );

  const toggleImagery = React.useCallback(() => {
    const next = toggleViewerImagery(
      viewerRef.current as ViewerWithPicker | null
    );
    if (next !== null) setImageryOpen(next);
  }, []);

  const registerViewer = React.useCallback(
    (viewer: Viewer | null, cesium?: typeof import("cesium")) => {
      viewerRef.current = viewer;
      if (cesium) cesiumRef.current = cesium;
      setActive(Boolean(viewer));
      setImageryOpen(false);
      const picker = (viewer as ViewerWithPicker | null)?.baseLayerPicker;
      setImageryAvailable(Boolean(picker));
      // Cesium's BaseLayerPicker installs a capture-phase document `pointerdown`
      // handler that closes its dropdown on any click outside its *own* (now
      // CSS-hidden) toggle button. The Header's imagery button counts as
      // "outside", so that handler closed the panel on the button's pointerdown
      // and the click then re-opened it — the toggle could never close, and
      // outside clicks closed the panel without telling React. The Header now
      // owns open/close + outside-dismiss, so detach Cesium's handler.
      if (picker?._closeDropDown) {
        document.removeEventListener("pointerdown", picker._closeDropDown, true);
        document.removeEventListener("mousedown", picker._closeDropDown, true);
        document.removeEventListener("touchstart", picker._closeDropDown, true);
      }
      // A mode switch rebuilds the viewer (defaulting back to 3D); re-apply the
      // user's chosen projection instantly (no animation) so it just survives
      // the rebuild rather than morphing on screen.
      if (viewer) applyScene(viewer, sceneModeRef.current, 0);
    },
    [applyScene]
  );

  const captureGlobe = React.useCallback((): string | null => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return null;
    return captureScene(viewer.scene);
  }, []);

  // Build the narrow capture surface (positionCamera/render/tilesLoaded/canvas)
  // over the live viewer. setView is instant (no animation) so the rendered
  // frame is deterministic; the destination is the country's centroid at the
  // tuned height, looking straight down.
  const countryCaptureScene = React.useCallback(
    (viewer: Viewer): CountryCaptureScene => ({
      positionCamera: (target: CameraTarget) => {
        const cesium = cesiumRef.current;
        if (!cesium) return; // globe not ready; snapshot the current view
        viewer.scene.camera.setView({
          destination: cesium.Cartesian3.fromDegrees(
            target.lon,
            target.lat,
            target.heightMeters
          ),
        });
      },
      render: () => viewer.scene.render(),
      tilesLoaded: () => viewer.scene.globe.tilesLoaded,
      canvas: viewer.scene.canvas,
    }),
    []
  );

  // Snapshot the camera so we can put the user's view back after capturing. We
  // clone position/direction/up (Cesium reuses these Cartesian3 instances per
  // frame, so we must copy, not alias) and restore via a single instant setView.
  const saveCamera = React.useCallback((viewer: Viewer) => {
    const cam = viewer.scene.camera;
    return {
      destination: cam.position.clone(),
      orientation: {
        direction: cam.direction.clone(),
        up: cam.up.clone(),
      },
    };
  }, []);

  const captureCountryGlobe = React.useCallback(
    async (country: ReportCountryCode): Promise<string | null> => {
      const viewer = viewerRef.current;
      if (!viewer || viewer.isDestroyed()) return null;
      const saved = saveCamera(viewer);
      try {
        return await captureCountryScene(countryCaptureScene(viewer), country);
      } finally {
        if (!viewer.isDestroyed()) viewer.scene.camera.setView(saved);
      }
    },
    [countryCaptureScene, saveCamera]
  );

  const captureAllCountryGlobes = React.useCallback(async (
    options: CaptureReadyOptions = {}
  ): Promise<Partial<Record<ReportCountryCode, string>>> => {
    // The report chat can submit before Cesium has finished mounting; wait
    // (bounded) for the viewer to register rather than silently returning {}.
    const viewer = await awaitRegisteredViewer(viewerRef, options);
    if (!viewer || viewer.isDestroyed()) return {};
    const saved = saveCamera(viewer);
    const result: Partial<Record<ReportCountryCode, string>> = {};
    try {
      // Sequential: one shared canvas, so captures must not overlap.
      for (const country of REPORT_COUNTRY_CODES) {
        const img = await captureCountryScene(
          countryCaptureScene(viewer),
          country
        );
        if (img) result[country] = img;
      }
    } finally {
      if (!viewer.isDestroyed()) viewer.scene.camera.setView(saved);
    }
    return result;
  }, [countryCaptureScene, saveCamera]);

  const value = React.useMemo<GlobeControlsValue>(
    () => ({
      mode,
      setMode,
      sceneMode,
      setSceneMode,
      imageryOpen,
      toggleImagery,
      imageryAvailable,
      active,
      railOpen,
      toggleRail,
      roiVisible,
      toggleRoi,
      registerViewer,
      captureGlobe,
      captureCountryGlobe,
      captureAllCountryGlobes,
    }),
    [
      mode,
      sceneMode,
      setSceneMode,
      imageryOpen,
      toggleImagery,
      imageryAvailable,
      active,
      railOpen,
      toggleRail,
      roiVisible,
      toggleRoi,
      registerViewer,
      captureGlobe,
      captureCountryGlobe,
      captureAllCountryGlobes,
    ]
  );

  return (
    <GlobeControlsContext.Provider value={value}>
      {children}
    </GlobeControlsContext.Provider>
  );
}

export function useGlobeControls(): GlobeControlsValue {
  const ctx = React.useContext(GlobeControlsContext);
  if (ctx === null) {
    throw new Error(
      "useGlobeControls must be used within a GlobeControlsProvider"
    );
  }
  return ctx;
}
