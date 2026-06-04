"use client";

// Sensor list & selection (#9c) + observer-relative pass / look-angle tool
// (#9i). Selecting a sensor drives the globe coverage ring; with a satellite
// also selected, the panel shows the live look angle and upcoming passes
// computed client-side from the object's TLE.

import React from "react";
import CollapsiblePanel from "./CollapsiblePanel";
import { useSensor } from "../context/SensorContext";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { SENSORS } from "../data/sensors";
import {
  lookAngleAt,
  predictPasses,
  type LookAngle,
  type SatPass,
} from "../utils/lookAngles";
import { useApiQuery } from "@/lib/api/useApiQuery";
import { queryKeys } from "@/lib/api/queryKeys";
import type { ObjectDetail } from "@/lib/orbital-engine";
import * as s from "./panelStyles";

const LIVE_MS = 1000;

function hhmm(d: Date): string {
  return d.toISOString().slice(11, 16) + "Z";
}

function rowStyle(active: boolean): React.CSSProperties {
  return {
    ...s.listItem,
    background: active ? "rgba(120, 220, 120, 0.18)" : "transparent",
  };
}

export const SensorPanel: React.FunctionComponent = () => {
  const { activeSensorId, setActiveSensorId, activeSensor } = useSensor();
  const { selectedId } = useSelectedSatellite();

  const [live, setLive] = React.useState<LookAngle | null>(null);

  const { data: detail } = useApiQuery<ObjectDetail>({
    queryKey: queryKeys.catalogDetail(selectedId ?? ""),
    url: `/api/catalog/${encodeURIComponent(selectedId ?? "")}`,
    options: { enabled: selectedId !== null },
  });

  const line1 = detail?.tle_line1;
  const line2 = detail?.tle_line2;

  // Live look angle for the active sensor + selected object (reset by render
  // gating — no synchronous setState in the effect body). `activeSensor` is a
  // stable context value, so it's safe as a dependency.
  React.useEffect(() => {
    if (!activeSensor || !line1 || !line2) return;
    const observer = {
      latDeg: activeSensor.latDeg,
      lonDeg: activeSensor.lonDeg,
      altKm: activeSensor.altKm,
    };
    const tick = () => setLive(lookAngleAt(line1, line2, observer, new Date()));
    tick();
    const handle = window.setInterval(tick, LIVE_MS);
    return () => window.clearInterval(handle);
  }, [activeSensor, line1, line2]);

  // Predicted passes — pure derivation from sensor + object, no effect needed.
  const passes = React.useMemo<SatPass[]>(() => {
    if (!activeSensor || !line1 || !line2) return [];
    return predictPasses(
      line1,
      line2,
      {
        latDeg: activeSensor.latDeg,
        lonDeg: activeSensor.lonDeg,
        altKm: activeSensor.altKm,
      },
      { durationHours: 24, minElevationDeg: 10 }
    );
  }, [activeSensor, line1, line2]);

  return (
    <CollapsiblePanel title="Sensors & Passes">
      <ul style={s.list}>
        {SENSORS.map((sensor) => (
          <li
            key={sensor.id}
            style={rowStyle(activeSensorId === sensor.id)}
            onClick={() =>
              setActiveSensorId(
                activeSensorId === sensor.id ? null : sensor.id
              )
            }
          >
            <span>{sensor.name}</span>
            <span style={s.muted}>{sensor.country}</span>
          </li>
        ))}
      </ul>

      <div style={{ borderTop: "1px solid rgba(255,255,255,0.08)", paddingTop: 8 }}>
        {!activeSensor && <p style={s.muted}>Select a sensor for look angles.</p>}
        {activeSensor && selectedId === null && (
          <p style={s.muted}>Select a satellite to compute passes.</p>
        )}
        {activeSensor && selectedId !== null && (
          <>
            <p style={{ ...s.muted, margin: "0 0 4px" }}>
              {activeSensor.name} → {detail?.object_name ?? selectedId}
            </p>
            <div style={s.listItem}>
              <span style={s.muted}>Az / El</span>
              <span>
                {live
                  ? `${live.azimuthDeg.toFixed(1)}° / ${live.elevationDeg.toFixed(1)}°`
                  : "—"}
              </span>
            </div>
            <div style={s.listItem}>
              <span style={s.muted}>Range</span>
              <span>{live ? `${live.rangeKm.toFixed(0)} km` : "—"}</span>
            </div>
            <p style={{ ...s.muted, margin: "8px 0 2px" }}>
              Next passes (24 h, ≥10°)
            </p>
            {passes.length === 0 ? (
              <p style={s.muted}>No passes in window.</p>
            ) : (
              <ul style={s.list}>
                {passes.map((p, i) => (
                  <li key={i} style={s.listItem}>
                    <span>
                      {hhmm(p.riseTime)}–{hhmm(p.setTime)}
                    </span>
                    <span style={s.muted}>
                      max {p.maxElevationDeg.toFixed(0)}°
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </CollapsiblePanel>
  );
};

export default SensorPanel;
