"use client";

// Sensor-volume overlay state. When enabled, the globe draws the SELECTED
// satellite's onboard sensor field-of-view cone + ground footprint (the area it
// can observe). The globe (CesiumComponent) reads this; the per-satellite info
// sidebar drives the toggle + half-angle. Deliberately distinct from the
// `SensorContext` ground-sensor system (sites that observe satellites — the
// inverse concept).

import React from "react";
import { DEFAULT_SENSOR_HALF_ANGLE_DEG } from "../utils/sensorVolume";

interface SensorVolumeContextValue {
  /** Whether to draw the selected satellite's sensor volume. */
  enabled: boolean;
  setEnabled: (v: boolean) => void;
  /** Sensor half-cone (nadir) angle in degrees — drives the footprint size. */
  halfAngleDeg: number;
  setHalfAngleDeg: (deg: number) => void;
}

const SensorVolumeContext =
  React.createContext<SensorVolumeContextValue | null>(null);

export function SensorVolumeProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [enabled, setEnabled] = React.useState(false);
  const [halfAngleDeg, setHalfAngleDeg] = React.useState(
    DEFAULT_SENSOR_HALF_ANGLE_DEG
  );
  const value = React.useMemo(
    () => ({ enabled, setEnabled, halfAngleDeg, setHalfAngleDeg }),
    [enabled, halfAngleDeg]
  );
  return (
    <SensorVolumeContext.Provider value={value}>
      {children}
    </SensorVolumeContext.Provider>
  );
}

export function useSensorVolume(): SensorVolumeContextValue {
  const ctx = React.useContext(SensorVolumeContext);
  if (ctx === null) {
    throw new Error(
      "useSensorVolume must be used within a SensorVolumeProvider"
    );
  }
  return ctx;
}
