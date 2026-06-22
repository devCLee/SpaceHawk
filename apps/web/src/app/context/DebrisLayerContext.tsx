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
    }),
    [visible, heatmap, hiddenRisks]
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
