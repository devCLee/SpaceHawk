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
import { SensorProvider } from "../context/SensorContext";
import { SensorVolumeProvider } from "../context/SensorVolumeContext";
import { useCatalog } from "@/lib/api/useCatalog";

export const DashboardShell: React.FunctionComponent = () => {
  // Catalog fetched client-side (and cached/shared via React Query) rather than
  // arriving as an RSC prop. The globe mounts immediately and renders points
  // once the fetch resolves.
  const { data: tleEntries } = useCatalog();
  return (
    <SelectedSatelliteProvider>
      <CatalogViewProvider>
        <SensorProvider>
          <SensorVolumeProvider>
            <CesiumWrapper positions={[]} tleEntries={tleEntries ?? []} />
            <ControlRail />
            <SatelliteInfoPanel />
          </SensorVolumeProvider>
        </SensorProvider>
      </CatalogViewProvider>
    </SelectedSatelliteProvider>
  );
};

export default DashboardShell;
