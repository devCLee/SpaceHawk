"use client";

// Debris-layer overlay state. When visible, the globe draws the tracked-debris
// population as a second GPU point layer coloured by collision-risk level
// (Critical/High/Medium/Low); `heatmap` independently toggles the 2D geographic
// density heatmap overlay (DebrisHeatmap2D). The globe (CesiumComponent) reads
// `visible`/`hiddenRisks`, the heatmap overlay reads `heatmap`, and the
// DebrisPanel drives all the toggles. Deliberately distinct from the object-class
// DEBRIS category in CatalogViewContext (which colours the main catalog layer).

import React from "react";
import type { DebrisRiskLevel } from "../data/visualization";
import { canvasToBase64Png } from "@/lib/reportCapture";

interface DebrisLayerContextValue {
  /** Whether the debris layer is drawn on the globe. */
  visible: boolean;
  setVisible: (v: boolean) => void;
  toggleVisible: () => void;
  /** Show the 2D geographic (lon×lat) debris-density heatmap overlay. */
  heatmap: boolean;
  setHeatmap: (v: boolean) => void;
  /** Risk levels hidden from the layer (legend show/hide + risk filter). */
  hiddenRisks: DebrisRiskLevel[];
  isRiskHidden: (level: DebrisRiskLevel) => boolean;
  toggleRisk: (level: DebrisRiskLevel) => void;
  /** DebrisHeatmap2D registers its <canvas> here while mounted (null on unmount)
   *  so the report capture (R8) can snapshot the 2D heatmap when it's open. */
  registerHeatmapCanvas: (canvas: HTMLCanvasElement | null) => void;
  /** Snapshot the 2D heatmap as a base64 PNG (no data-URL prefix), or null when
   *  the heatmap overlay is closed / not registered. */
  captureHeatmap: () => string | null;
}

const DebrisLayerContext = React.createContext<DebrisLayerContextValue | null>(
  null
);

export function DebrisLayerProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [visible, setVisible] = React.useState(false);
  const [heatmap, setHeatmap] = React.useState(false);
  const [hiddenRisks, setHiddenRisks] = React.useState<DebrisRiskLevel[]>([]);
  const heatmapCanvasRef = React.useRef<HTMLCanvasElement | null>(null);

  const registerHeatmapCanvas = React.useCallback(
    (canvas: HTMLCanvasElement | null) => {
      heatmapCanvasRef.current = canvas;
    },
    []
  );
  const captureHeatmap = React.useCallback((): string | null => {
    const canvas = heatmapCanvasRef.current;
    return canvas ? canvasToBase64Png(canvas) : null;
  }, []);

  const value = React.useMemo<DebrisLayerContextValue>(
    () => ({
      visible,
      setVisible,
      toggleVisible: () => setVisible((v) => !v),
      heatmap,
      setHeatmap,
      hiddenRisks,
      isRiskHidden: (level) => hiddenRisks.includes(level),
      toggleRisk: (level) =>
        setHiddenRisks((prev) =>
          prev.includes(level)
            ? prev.filter((l) => l !== level)
            : [...prev, level]
        ),
      registerHeatmapCanvas,
      captureHeatmap,
    }),
    [visible, heatmap, hiddenRisks, registerHeatmapCanvas, captureHeatmap]
  );

  return (
    <DebrisLayerContext.Provider value={value}>
      {children}
    </DebrisLayerContext.Provider>
  );
}

export function useDebrisLayer(): DebrisLayerContextValue {
  const ctx = React.useContext(DebrisLayerContext);
  if (ctx === null) {
    throw new Error("useDebrisLayer must be used within a DebrisLayerProvider");
  }
  return ctx;
}
