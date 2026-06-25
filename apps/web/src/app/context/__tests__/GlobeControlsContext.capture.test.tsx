// Per-country globe capture (feat/hwpx-report-pipeline): GlobeControls drives the
// live Cesium camera over each report country (NK/CN/RU/JP), waits for tiles, and
// snapshots — restoring the user's prior camera afterward. Cesium is mocked: the
// only value GlobeControls imports from it is `Cartesian3` (for setView
// destinations + camera-state cloning), so a tiny stub stands in for the whole lib.

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, cleanup } from "@testing-library/react";

// Mock `cesium` BEFORE importing the context (which imports Cartesian3 from it).
vi.mock("cesium", () => {
  class Cartesian3 {
    constructor(
      public x = 0,
      public y = 0,
      public z = 0
    ) {}
    clone() {
      return new Cartesian3(this.x, this.y, this.z);
    }
    static fromDegrees(lon: number, lat: number, height: number) {
      return new Cartesian3(lon, lat, height);
    }
  }
  return { Cartesian3 };
});

import {
  GlobeControlsProvider,
  useGlobeControls,
} from "../GlobeControlsContext";
import type { Viewer } from "cesium";

// A minimal fake Cesium viewer: a camera with setView + clonable position/
// direction/up, a scene whose globe.tilesLoaded we can flip, render() counter,
// and a canvas that encodes to a per-call data URL so each country's snapshot is
// distinguishable.
function makeFakeViewer(opts?: {
  tilesLoadedAfter?: number; // becomes true after N renders (default: always)
  dataUrlFor?: (renderCount: number) => string;
}) {
  let renders = 0;
  const setView = vi.fn();
  const camera = {
    position: { x: 1, y: 2, z: 3, clone: vi.fn(() => ({ x: 1, y: 2, z: 3 })) },
    direction: { x: 0, y: 0, z: -1, clone: vi.fn(() => ({ x: 0, y: 0, z: -1 })) },
    up: { x: 0, y: 1, z: 0, clone: vi.fn(() => ({ x: 0, y: 1, z: 0 })) },
    setView,
  };
  const canvas = {
    width: 100,
    height: 100,
    toDataURL: vi.fn(() => {
      const url = opts?.dataUrlFor
        ? opts.dataUrlFor(renders)
        : "data:image/png;base64,QUJD"; // base64("ABC")
      return url;
    }),
  } as unknown as HTMLCanvasElement;
  const scene = {
    camera,
    canvas,
    globe: {
      get tilesLoaded() {
        return opts?.tilesLoadedAfter === undefined
          ? true
          : renders >= opts.tilesLoadedAfter;
      },
    },
    render: vi.fn(() => {
      renders += 1;
    }),
  };
  const viewer = {
    scene,
    isDestroyed: () => false,
    // The provider also reads baseLayerPicker on register; absent is fine.
  } as unknown as Viewer;
  return { viewer, camera, setView, scene, renderCount: () => renders };
}

function renderControls() {
  return renderHook(() => useGlobeControls(), {
    wrapper: ({ children }: { children: React.ReactNode }) => (
      <GlobeControlsProvider>{children}</GlobeControlsProvider>
    ),
  });
}

// CesiumComponent hands the cesium namespace to registerViewer; capture's
// positionCamera builds destinations via cesium.Cartesian3.fromDegrees. Stub it.
const FAKE_CESIUM = {
  Cartesian3: { fromDegrees: (lon: number, lat: number, h: number) => ({ lon, lat, h }) },
} as unknown as typeof import("cesium");

beforeEach(() => {
  vi.useRealTimers();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("GlobeControls per-country capture", () => {
  it("returns null when no viewer is registered", async () => {
    const { result } = renderControls();
    await act(async () => {
      expect(await result.current.captureCountryGlobe("NK")).toBeNull();
    });
    // readyTimeoutMs:0 -> don't wait for a viewer that will never register.
    expect(
      await act(() =>
        result.current.captureAllCountryGlobes({ readyTimeoutMs: 0 })
      )
    ).toEqual({});
  });

  it("waits for a late-registered viewer, then captures all four", async () => {
    // The report can submit before Cesium mounts: no viewer at call time, but
    // one registers during the readiness wait. Capture must pick it up (not
    // silently return {}). The injected sleep registers the viewer on first poll.
    const { viewer } = makeFakeViewer({
      dataUrlFor: (n) => `data:image/png;base64,${btoa(`g${n}`)}`,
    });
    const { result } = renderControls();

    let globes: Partial<Record<string, string>> = {};
    await act(async () => {
      let registered = false;
      const sleep = async () => {
        if (!registered) {
          registered = true;
          result.current.registerViewer(viewer, FAKE_CESIUM); // viewer arrives mid-wait
        }
      };
      globes = await result.current.captureAllCountryGlobes({
        readyTimeoutMs: 1000,
        pollMs: 1,
        sleep,
      });
    });
    expect(Object.keys(globes).sort()).toEqual(["CN", "JP", "NK", "RU"]);
  });

  it("positions the camera over the country and returns the base64 snapshot", async () => {
    const { viewer, setView } = makeFakeViewer();
    const { result } = renderControls();
    act(() => result.current.registerViewer(viewer, FAKE_CESIUM));

    let out: string | null = null;
    await act(async () => {
      out = await result.current.captureCountryGlobe("NK");
    });
    expect(out).toBe("QUJD");
    // setView called twice: once to frame NK, once to restore the prior camera.
    expect(setView).toHaveBeenCalledTimes(2);
    // The first setView destination is the (mocked) Cartesian3 from NK's centroid.
    const framed = setView.mock.calls[0][0] as { destination: unknown };
    expect(framed.destination).toBeDefined();
  });

  it("restores the prior camera after capture (last setView is the saved state)", async () => {
    const { viewer, camera, setView } = makeFakeViewer();
    const { result } = renderControls();
    act(() => result.current.registerViewer(viewer, FAKE_CESIUM));

    await act(async () => {
      await result.current.captureCountryGlobe("CN");
    });
    // The saved camera was cloned on entry...
    expect(camera.position.clone).toHaveBeenCalled();
    // ...and the LAST setView restored that saved {destination, orientation}.
    const restore = setView.mock.calls.at(-1)![0] as {
      destination: unknown;
      orientation: { direction: unknown; up: unknown };
    };
    expect(restore.orientation).toBeDefined();
    expect(restore.orientation.direction).toEqual({ x: 0, y: 0, z: -1 });
    expect(restore.orientation.up).toEqual({ x: 0, y: 1, z: 0 });
  });

  it("captures all four countries and restores the camera once", async () => {
    // Each country's snapshot is tagged with its render count so they differ.
    const { viewer, setView } = makeFakeViewer({
      dataUrlFor: (n) => `data:image/png;base64,${btoa(`f${n}`)}`,
    });
    const { result } = renderControls();
    act(() => result.current.registerViewer(viewer, FAKE_CESIUM));

    let globes: Partial<Record<string, string>> = {};
    await act(async () => {
      globes = await result.current.captureAllCountryGlobes();
    });
    expect(Object.keys(globes).sort()).toEqual(["CN", "JP", "NK", "RU"]);
    // 4 framing setViews + exactly ONE restore at the end = 5 total.
    expect(setView).toHaveBeenCalledTimes(5);
  });

  it("gives up tile-waiting after the timeout (capture never hangs)", async () => {
    // tilesLoaded never becomes true; with a short timeout the capture must
    // still resolve (snapshotting whatever is rendered) rather than hang.
    const { viewer } = makeFakeViewer({ tilesLoadedAfter: Number.POSITIVE_INFINITY });
    const { result } = renderControls();
    act(() => result.current.registerViewer(viewer, FAKE_CESIUM));

    let out: string | null = null;
    const start = Date.now();
    await act(async () => {
      out = await result.current.captureCountryGlobe("JP");
    });
    // It resolved (did not hang) and produced the best-effort snapshot.
    expect(out).toBe("QUJD");
    // Bounded: well under the test runner's patience even though tiles never load.
    expect(Date.now() - start).toBeLessThan(10000);
  });
});
