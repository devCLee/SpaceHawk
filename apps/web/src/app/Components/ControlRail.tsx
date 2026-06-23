"use client";

// Left control rail — stacks the analyst panels (search, filters, sensors,
// collisions). Each branch adds its panel here.

import React from "react";
import { useGlobeControls } from "../context/GlobeControlsContext";
import SearchPanel from "./SearchPanel";
import VisualizationPanel from "./VisualizationPanel";
import SensorPanel from "./SensorPanel";
import CollisionsPanel from "./CollisionsPanel";
import DebrisPanel from "./DebrisPanel";
import ManeuverPanel from "./ManeuverPanel";
import ReportChatPanel from "./ReportChatPanel";
import AlertCenter from "./AlertCenter";
import {
  CountriesPanel,
  ConstellationsPanel,
  WatchlistPanel,
} from "./FilterPanels";

export const ControlRail: React.FunctionComponent = () => {
  // The Header's panel-left button drives railOpen; closed slides the rail off
  // the left edge (pointer-events off so the hidden rail can't catch globe clicks).
  const { railOpen } = useGlobeControls();
  return (
    <div
      aria-hidden={!railOpen}
      style={{
        position: "absolute",
        top: 72,
        left: 8,
        zIndex: 15,
        width: 300,
        // Bottom reservation (120px) clears Cesium's animation widget
        // (.cesium-viewer-animationContainer, 169x112px, bottom-left) plus an
        // 8px gap so the rail never overlaps the shuttle-ring playback control.
        maxHeight: "calc(100vh - 192px)",
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        transform: railOpen ? "translateX(0)" : "translateX(-110%)",
        transition: "transform 0.22s ease",
        pointerEvents: railOpen ? "auto" : "none",
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
      <ReportChatPanel />
      <AlertCenter />
      <WatchlistPanel />
    </div>
  );
};

export default ControlRail;
