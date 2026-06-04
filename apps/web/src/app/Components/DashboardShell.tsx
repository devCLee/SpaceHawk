"use client";

// Client shell for the operational dashboard. Provides the selected-satellite
// context to the globe and (in later branches) the info sidebar / search /
// watchlist panels, all of which read or set the same selection.

import React from "react";
import CesiumWrapper from "./CesiumWrapper";
import { SelectedSatelliteProvider } from "../context/SelectedSatelliteContext";
import type { TleObject } from "../utils/sgp4FromTle";

export const DashboardShell: React.FunctionComponent<{
  tleEntries: TleObject[];
}> = ({ tleEntries }) => {
  return (
    <SelectedSatelliteProvider>
      <CesiumWrapper positions={[]} tleEntries={tleEntries} />
    </SelectedSatelliteProvider>
  );
};

export default DashboardShell;
