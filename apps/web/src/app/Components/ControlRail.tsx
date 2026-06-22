"use client";

// Left control rail — stacks the analyst panels (search, filters, sensors,
// collisions). Each branch adds its panel here.

import React from "react";
import SearchPanel from "./SearchPanel";
import VisualizationPanel from "./VisualizationPanel";
import SensorPanel from "./SensorPanel";
import CollisionsPanel from "./CollisionsPanel";
import DebrisPanel from "./DebrisPanel";
import ManeuverPanel from "./ManeuverPanel";
import AlertCenter from "./AlertCenter";
import {
  CountriesPanel,
  ConstellationsPanel,
  WatchlistPanel,
} from "./FilterPanels";

export const ControlRail: React.FunctionComponent = () => {
  return (
    <div
      style={{
        position: "absolute",
        top: 72,
        left: 8,
        zIndex: 15,
        width: 300,
        maxHeight: "calc(100vh - 136px)",
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <SearchPanel />
      <VisualizationPanel />
      <CountriesPanel />
      <ConstellationsPanel />
      <SensorPanel />
      <CollisionsPanel />
      <DebrisPanel />
      <ManeuverPanel />
      <AlertCenter />
      <WatchlistPanel />
    </div>
  );
};

export default ControlRail;
