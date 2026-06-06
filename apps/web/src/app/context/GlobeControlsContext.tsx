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
import type { Viewer } from "cesium";

/** Online = Cesium Ion imagery/terrain; offline = bundled Natural Earth II. */
export type GlobeMode = "offline" | "online";
/** Cesium's three scene projections (SceneModePicker parity). */
export type SceneMode = "3D" | "2D" | "Columbus";

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
  /** CesiumComponent registers its viewer on build and `null` on teardown. */
  registerViewer: (viewer: Viewer | null) => void;
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

  const viewerRef = React.useRef<Viewer | null>(null);
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
    (viewer: Viewer | null) => {
      viewerRef.current = viewer;
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
      registerViewer,
    }),
    [
      mode,
      sceneMode,
      setSceneMode,
      imageryOpen,
      toggleImagery,
      imageryAvailable,
      active,
      registerViewer,
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
