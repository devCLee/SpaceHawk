"use client";

// Client shell for the operational dashboard. Provides the selected-satellite
// context to the globe and (in later branches) the info sidebar / search /
// watchlist panels, all of which read or set the same selection.

import React from "react";
import CesiumWrapper from "./CesiumWrapper";
import SatelliteInfoPanel from "./SatelliteInfoPanel";
import DebrisInfoPanel from "./DebrisInfoPanel";
import ControlRail from "./ControlRail";
import { SelectedSatelliteProvider } from "../context/SelectedSatelliteContext";
import { CatalogViewProvider } from "../context/CatalogViewContext";
import { SensorProvider } from "../context/SensorContext";
import { SensorVolumeProvider } from "../context/SensorVolumeContext";
import { DebrisLayerProvider } from "../context/DebrisLayerContext";
import { useCatalog } from "@/lib/api/useCatalog";
import { useDebris } from "@/lib/api/useDebris";

export const DashboardShell: React.FunctionComponent = () => {
  // Catalog + debris fetched client-side (and cached/shared via React Query)
  // rather than arriving as RSC props. The globe mounts immediately and renders
  // points once each fetch resolves.
  const { data: tleEntries } = useCatalog();
  const { data: debrisEntries } = useDebris();
  return (
    <SelectedSatelliteProvider>
      <CatalogViewProvider>
        <SensorProvider>
          <SensorVolumeProvider>
            <DebrisLayerProvider>
              <CesiumWrapper
                positions={[]}
                tleEntries={tleEntries ?? []}
                debrisEntries={debrisEntries ?? []}
              />
              <ControlRail />
              <SatelliteInfoPanel />
              <DebrisInfoPanel />
            </DebrisLayerProvider>
          </SensorVolumeProvider>
        </SensorProvider>
      </CatalogViewProvider>
    </SelectedSatelliteProvider>
  );
};

export default DashboardShell;
