"use client";

// Shared selected-satellite state (dev-plan Stage 3 "General UX: selected-
// satellite React Context"). The globe sets the selection on click; sibling
// panels (info sidebar, search, watchlist) read it — no prop drilling across
// the dynamically-imported Cesium boundary.

import React from "react";

interface SelectedSatelliteContextValue {
  /** Canonical catalog id (USOID) of the selected object, or null. */
  selectedId: string | null;
  setSelectedId: (id: string | null) => void;
}

const SelectedSatelliteContext =
  React.createContext<SelectedSatelliteContextValue | null>(null);

export function SelectedSatelliteProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const value = React.useMemo(
    () => ({ selectedId, setSelectedId }),
    [selectedId]
  );
  return (
    <SelectedSatelliteContext.Provider value={value}>
      {children}
    </SelectedSatelliteContext.Provider>
  );
}

export function useSelectedSatellite(): SelectedSatelliteContextValue {
  const ctx = React.useContext(SelectedSatelliteContext);
  if (ctx === null) {
    throw new Error(
      "useSelectedSatellite must be used within a SelectedSatelliteProvider"
    );
  }
  return ctx;
}
