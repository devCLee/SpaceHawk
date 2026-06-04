"use client";

// Left control rail — stacks the analyst panels (search, filters, sensors,
// collisions). Each branch adds its panel here.

import React from "react";
import SearchPanel from "./SearchPanel";
import SensorPanel from "./SensorPanel";
import CollisionsPanel from "./CollisionsPanel";
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
        top: 48,
        left: 8,
        zIndex: 15,
        width: 300,
        maxHeight: "calc(100vh - 112px)",
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <SearchPanel />
      <CountriesPanel />
      <ConstellationsPanel />
      <SensorPanel />
      <CollisionsPanel />
      <WatchlistPanel />
    </div>
  );
};

export default ControlRail;
