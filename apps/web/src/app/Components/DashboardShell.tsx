"use client";

// Client shell for the operational dashboard. Provides the selected-satellite
// context to the globe and (in later branches) the info sidebar / search /
// watchlist panels, all of which read or set the same selection.

import React from "react";
import CesiumWrapper from "./CesiumWrapper";
import SatelliteInfoPanel from "./SatelliteInfoPanel";
import ControlRail from "./ControlRail";
import { SelectedSatelliteProvider } from "../context/SelectedSatelliteContext";
import { CatalogViewProvider } from "../context/CatalogViewContext";
import type { TleObject } from "../utils/sgp4FromTle";

export const DashboardShell: React.FunctionComponent<{
  tleEntries: TleObject[];
}> = ({ tleEntries }) => {
  return (
    <SelectedSatelliteProvider>
      <CatalogViewProvider>
        <CesiumWrapper positions={[]} tleEntries={tleEntries} />
        <ControlRail />
        <SatelliteInfoPanel />
      </CatalogViewProvider>
    </SelectedSatelliteProvider>
  );
};

export default DashboardShell;
