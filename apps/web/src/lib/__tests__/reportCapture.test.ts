import { describe, it, expect, vi } from "vitest";
import {
  canvasToBase64Png,
  captureScene,
  captureReportImages,
  cameraTargetForCountry,
  captureCountryScene,
  waitForTilesLoaded,
  REPORT_COUNTRY_CODES,
  type CountryCaptureScene,
  type ReportCountryCode,
} from "@/lib/reportCapture";

// A minimal canvas stub: only width/height + toDataURL are read by the util.
function fakeCanvas(opts: {
  width?: number;
  height?: number;
  dataUrl?: string | (() => string);
}): HTMLCanvasElement {
  const { width = 100, height = 100, dataUrl } = opts;
  return {
    width,
    height,
    toDataURL: vi.fn(() =>
      typeof dataUrl === "function" ? dataUrl() : (dataUrl ?? "")
    ),
  } as unknown as HTMLCanvasElement;
}

describe("canvasToBase64Png", () => {
  it("strips the data-URL prefix and returns the base64 payload", () => {
    const canvas = fakeCanvas({
      dataUrl: "data:image/png;base64,QUJD", // base64("ABC")
    });
    expect(canvasToBase64Png(canvas)).toBe("QUJD");
  });

  it("returns null for a zero-sized canvas (toDataURL not even called)", () => {
    const canvas = fakeCanvas({ width: 0, dataUrl: "data:image/png;base64,QUJD" });
    expect(canvasToBase64Png(canvas)).toBeNull();
    expect(canvas.toDataURL).not.toHaveBeenCalled();
  });

  it("returns null when toDataURL throws (e.g. tainted canvas)", () => {
    const canvas = fakeCanvas({
      dataUrl: () => {
        throw new Error("SecurityError");
      },
    });
    expect(canvasToBase64Png(canvas)).toBeNull();
  });

  it("returns null for a non-PNG / empty data URL", () => {
    expect(canvasToBase64Png(fakeCanvas({ dataUrl: "data:," }))).toBeNull();
    expect(
      canvasToBase64Png(fakeCanvas({ dataUrl: "data:image/png;base64," }))
    ).toBeNull();
  });
});

describe("captureScene", () => {
  it("renders one frame before reading the canvas", () => {
    const canvas = fakeCanvas({ dataUrl: "data:image/png;base64,UE5H" });
    const render = vi.fn();
    expect(captureScene({ canvas, render })).toBe("UE5H");
    expect(render).toHaveBeenCalledOnce();
  });

  it("returns null when render throws", () => {
    const canvas = fakeCanvas({ dataUrl: "data:image/png;base64,UE5H" });
    const render = vi.fn(() => {
      throw new Error("lost context");
    });
    expect(captureScene({ canvas, render })).toBeNull();
  });
});

describe("captureReportImages", () => {
  it("returns undefined when nothing is capturable", () => {
    expect(captureReportImages({})).toBeUndefined();
    expect(
      captureReportImages({ scene: null, heatmapCanvas: null })
    ).toBeUndefined();
  });

  it("files the current globe view under NK and includes the heatmap", () => {
    const scene = {
      canvas: fakeCanvas({ dataUrl: "data:image/png;base64,R0xPQkU" }), // GLOBE
      render: vi.fn(),
    };
    const heatmapCanvas = fakeCanvas({
      dataUrl: "data:image/png;base64,SEVBVA", // HEAT
    });
    expect(captureReportImages({ scene, heatmapCanvas })).toEqual({
      country_globes: { NK: "R0xPQkU" },
      debris_heatmap: "SEVBVA",
    });
  });

  it("omits an image whose canvas fails to encode", () => {
    const scene = {
      canvas: fakeCanvas({ dataUrl: "data:image/png;base64,R0xPQkU" }),
      render: vi.fn(),
    };
    // Heatmap canvas yields a blank (prefix-only) data URL -> dropped.
    const heatmapCanvas = fakeCanvas({ dataUrl: "data:image/png;base64," });
    expect(captureReportImages({ scene, heatmapCanvas })).toEqual({
      country_globes: { NK: "R0xPQkU" },
    });
  });
});

describe("cameraTargetForCountry", () => {
  it("resolves a distinct centroid + height for each report country", () => {
    const targets = REPORT_COUNTRY_CODES.map((c) => cameraTargetForCountry(c));
    // Every country has a finite lon/lat and a positive camera height.
    for (const target of targets) {
      expect(Number.isFinite(target.lon)).toBe(true);
      expect(Number.isFinite(target.lat)).toBe(true);
      expect(target.heightMeters).toBeGreaterThan(0);
      expect(target.lon).toBeGreaterThanOrEqual(-180);
      expect(target.lon).toBeLessThanOrEqual(180);
      expect(target.lat).toBeGreaterThanOrEqual(-90);
      expect(target.lat).toBeLessThanOrEqual(90);
    }
    // The four centroids are distinct (no two countries share a target lon/lat).
    const keys = new Set(targets.map((t) => `${t.lon},${t.lat}`));
    expect(keys.size).toBe(REPORT_COUNTRY_CODES.length);
  });

  it("places North Korea's centroid in the Korean peninsula box", () => {
    const nk = cameraTargetForCountry("NK");
    expect(nk.lon).toBeGreaterThan(124);
    expect(nk.lon).toBeLessThan(131);
    expect(nk.lat).toBeGreaterThan(37);
    expect(nk.lat).toBeLessThan(43);
  });
});

// A capture-scene stub: records positionCamera/render calls, reports tilesLoaded
// from a script (one boolean per poll), and encodes a fixed canvas data URL.
function fakeCaptureScene(opts: {
  dataUrl?: string;
  tilesLoadedScript?: boolean[];
  onPosition?: () => void;
}): {
  scene: CountryCaptureScene;
  renderCount: () => number;
  positions: () => number;
} {
  const { dataUrl = "data:image/png;base64,Q05U", tilesLoadedScript } = opts;
  let renders = 0;
  let positions = 0;
  let pollIndex = 0;
  const scene: CountryCaptureScene = {
    positionCamera: () => {
      positions += 1;
      opts.onPosition?.();
    },
    render: () => {
      renders += 1;
    },
    tilesLoaded: () => {
      if (!tilesLoadedScript) return true;
      const v = tilesLoadedScript[Math.min(pollIndex, tilesLoadedScript.length - 1)];
      pollIndex += 1;
      return v;
    },
    canvas: fakeCanvas({ dataUrl }),
  };
  return { scene, renderCount: () => renders, positions: () => positions };
}

describe("waitForTilesLoaded", () => {
  it("returns as soon as tiles are loaded (renders the initial frame)", async () => {
    const { scene, renderCount } = fakeCaptureScene({
      tilesLoadedScript: [true],
    });
    const sleep = vi.fn(async () => {});
    await waitForTilesLoaded(scene, { sleep });
    // One up-front render; no polling sleep needed since tiles were ready.
    expect(renderCount()).toBe(1);
    expect(sleep).not.toHaveBeenCalled();
  });

  it("polls (rendering each cycle) until tiles load", async () => {
    const { scene, renderCount } = fakeCaptureScene({
      tilesLoadedScript: [false, false, true],
    });
    const sleep = vi.fn(async () => {});
    await waitForTilesLoaded(scene, { sleep, pollMs: 10 });
    // up-front render + a render after each of the two false polls.
    expect(renderCount()).toBe(3);
    expect(sleep).toHaveBeenCalledTimes(2);
  });

  it("gives up after the timeout instead of hanging", async () => {
    // Tiles never load; a real (timer) sleep advances Date.now past the deadline.
    const { scene } = fakeCaptureScene({ tilesLoadedScript: [false] });
    const start = Date.now();
    await waitForTilesLoaded(scene, { timeoutMs: 30, pollMs: 5 });
    expect(Date.now() - start).toBeGreaterThanOrEqual(25);
  });
});

describe("captureCountryScene", () => {
  it("positions the camera, waits, then snapshots to base64", async () => {
    const { scene, positions } = fakeCaptureScene({
      dataUrl: "data:image/png;base64,Q05U", // base64("CNT")
      tilesLoadedScript: [true],
    });
    const out = await captureCountryScene(scene, "CN", { sleep: async () => {} });
    expect(out).toBe("Q05U");
    expect(positions()).toBe(1);
  });

  it("returns null when positioning the camera throws", async () => {
    const { scene } = fakeCaptureScene({
      onPosition: () => {
        throw new Error("camera unavailable");
      },
    });
    expect(
      await captureCountryScene(scene, "NK", { sleep: async () => {} })
    ).toBeNull();
  });

  it("returns null when the canvas cannot be encoded", async () => {
    const { scene } = fakeCaptureScene({
      dataUrl: "data:image/png;base64,", // blank -> encode fails
      tilesLoadedScript: [true],
    });
    expect(
      await captureCountryScene(scene, "JP", { sleep: async () => {} })
    ).toBeNull();
  });

  it("captures all four countries with distinct positioning calls", async () => {
    const results: Partial<Record<ReportCountryCode, string>> = {};
    for (const country of REPORT_COUNTRY_CODES) {
      const { scene } = fakeCaptureScene({
        dataUrl: `data:image/png;base64,${btoa(country)}`,
        tilesLoadedScript: [true],
      });
      const img = await captureCountryScene(scene, country, {
        sleep: async () => {},
      });
      if (img) results[country] = img;
    }
    expect(Object.keys(results).sort()).toEqual(
      [...REPORT_COUNTRY_CODES].sort()
    );
    expect(results.NK).toBe(btoa("NK"));
    expect(results.JP).toBe(btoa("JP"));
  });
});
