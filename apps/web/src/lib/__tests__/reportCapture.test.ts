import { describe, it, expect, vi } from "vitest";
import {
  canvasToBase64Png,
  captureScene,
  captureReportImages,
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
