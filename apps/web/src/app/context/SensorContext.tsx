"use client";

// Active-sensor selection (#9c). The sensor panel sets it; the globe draws the
// site marker + coverage ring, and the pass tool computes look angles from it.

import React from "react";
import { sensorById, type Sensor } from "../data/sensors";

interface SensorContextValue {
  activeSensorId: string | null;
  setActiveSensorId: (id: string | null) => void;
  activeSensor: Sensor | null;
}

const SensorContext = React.createContext<SensorContextValue | null>(null);

export function SensorProvider({ children }: { children: React.ReactNode }) {
  const [activeSensorId, setActiveSensorId] = React.useState<string | null>(
    null
  );
  const value = React.useMemo<SensorContextValue>(
    () => ({
      activeSensorId,
      setActiveSensorId,
      activeSensor: sensorById(activeSensorId),
    }),
    [activeSensorId]
  );
  return (
    <SensorContext.Provider value={value}>{children}</SensorContext.Provider>
  );
}

export function useSensor(): SensorContextValue {
  const ctx = React.useContext(SensorContext);
  if (ctx === null) {
    throw new Error("useSensor must be used within a SensorProvider");
  }
  return ctx;
}
