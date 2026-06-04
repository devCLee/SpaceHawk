"use client";

// Explainable-intent panel (Stage 6 #11/#14, roadmap O4). For the selected
// object it surfaces the maneuver evidence — Δv / RIC decomposition, the
// rule-based purpose class, and the V-pattern detection statistic — plus the
// object's behavioral baseline (cadence + Δv fingerprint). With nothing
// selected it lists recent maneuvers across the catalog; clicking a row focuses
// that object. Backed by the engine's MANEUVER_INTEL endpoint via the BFF;
// shows a graceful "unavailable" state when the service is offline or access is
// denied (the analyst-tier grant).

import React from "react";
import CollapsiblePanel from "./CollapsiblePanel";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { useApiQuery } from "@/lib/api/useApiQuery";
import { queryKeys } from "@/lib/api/queryKeys";
import type {
  BaselinesResult,
  Maneuver,
  ManeuverBaseline,
  ManeuversResult,
  ManeuverType,
} from "@/lib/orbital-engine";
import * as s from "./panelStyles";

const TYPE_COLOR: Record<ManeuverType, string> = {
  STATION_KEEPING: "#7dd87d",
  ORBIT_RAISE: "#5ab0ff",
  ORBIT_LOWER: "#5ab0ff",
  PHASING: "#ffd166",
  RPO: "#ff6b6b",
  UNKNOWN: "#7d8da0",
};

const TYPE_LABEL: Record<ManeuverType, string> = {
  STATION_KEEPING: "Station-keeping",
  ORBIT_RAISE: "Orbit raise",
  ORBIT_LOWER: "Orbit lower",
  PHASING: "Phasing",
  RPO: "RPO",
  UNKNOWN: "Unclassified",
};

function num(v: number | null | undefined, digits = 1): string {
  return v == null ? "n/a" : v.toFixed(digits);
}

const BaselineCard: React.FunctionComponent<{ baseline: ManeuverBaseline }> = ({
  baseline,
}) => (
  <div
    style={{
      border: "1px solid rgba(255,255,255,0.12)",
      borderRadius: 4,
      padding: "6px 8px",
      display: "flex",
      flexDirection: "column",
      gap: 3,
    }}
  >
    <div style={{ ...s.panelTitle, fontSize: 11 }}>Behavioral baseline</div>
    <div style={{ ...s.muted, fontSize: 11, display: "flex", gap: 10, flexWrap: "wrap" }}>
      <span>{baseline.sample_count} maneuvers</span>
      <span>
        cadence {num(baseline.mean_interval_days)}±{num(baseline.interval_mad_days)} d
      </span>
      <span>
        Δv {num(baseline.mean_delta_v_m_s)}±{num(baseline.delta_v_mad_m_s)} m/s
      </span>
    </div>
    <div style={{ ...s.muted, fontSize: 11 }}>
      {Object.entries(baseline.type_distribution)
        .map(([t, n]) => `${TYPE_LABEL[t as ManeuverType] ?? t}×${n}`)
        .join(" · ")}
    </div>
  </div>
);

const ManeuverRow: React.FunctionComponent<{
  m: Maneuver;
  onSelect: (id: string) => void;
}> = ({ m, onSelect }) => (
  <li
    style={{ ...s.listItem, flexDirection: "column", alignItems: "stretch", gap: 2 }}
    onClick={() => onSelect(m.object_id)}
  >
    <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
      <span>{m.object_name}</span>
      <span style={{ color: TYPE_COLOR[m.maneuver_type], fontWeight: 600 }}>
        {TYPE_LABEL[m.maneuver_type]}
      </span>
    </div>
    <div style={{ ...s.muted, fontSize: 11, display: "flex", gap: 10, flexWrap: "wrap" }}>
      <span>Δv {num(m.delta_v_m_s)} m/s</span>
      <span>ΔSMA {num(m.delta_sma_km, 2)} km</span>
      <span>conf {(m.confidence * 100).toFixed(0)}%</span>
    </div>
    {/* V-pattern + RIC evidence — the "why" behind the call (explainability). */}
    <div style={{ ...s.muted, fontSize: 11, display: "flex", gap: 10, flexWrap: "wrap" }}>
      <span title="Radial / In-track / Cross-track Δv">
        RIC {num(m.ric_radial_m_s)}/{num(m.ric_in_track_m_s)}/{num(m.ric_cross_track_m_s)}
      </span>
      <span title="Robust V-pattern detection statistic">σ {num(m.detection_statistic)}</span>
      <span>{new Date(m.detected_epoch).toLocaleDateString()}</span>
    </div>
  </li>
);

export const ManeuverPanel: React.FunctionComponent = () => {
  const { selectedId, setSelectedId } = useSelectedSatellite();

  const { data, isLoading, isError } = useApiQuery<ManeuversResult>({
    queryKey: queryKeys.maneuvers(selectedId ?? undefined),
    url: "/api/maneuvers",
    options: selectedId ? { params: { object_id: selectedId } } : undefined,
  });
  const { data: baselineData } = useApiQuery<BaselinesResult>({
    queryKey: queryKeys.baselines(),
    url: "/api/maneuvers/baselines",
  });

  const maneuvers = React.useMemo<Maneuver[]>(
    () => data?.maneuvers ?? [],
    [data]
  );
  const available = data?.available ?? null;
  const baseline = React.useMemo<ManeuverBaseline | null>(() => {
    if (!selectedId || !baselineData?.available) return null;
    return baselineData.baselines.find((b) => b.object_id === selectedId) ?? null;
  }, [selectedId, baselineData]);

  return (
    <CollapsiblePanel title="Maneuver Intel">
      {isLoading && <p style={s.muted}>Loading…</p>}
      {isError && <p style={s.error}>Maneuver intel unavailable.</p>}
      {!isLoading && !isError && available === false && (
        <p style={s.muted}>
          Maneuver intelligence is offline or outside your access. Detected
          maneuvers and behavioral baselines appear here for analyst-tier users.
        </p>
      )}
      {!isLoading && !isError && available && (
        <>
          {baseline && <BaselineCard baseline={baseline} />}
          {maneuvers.length === 0 ? (
            <p style={s.muted}>
              {selectedId
                ? "No maneuvers detected for this object."
                : "No maneuvers detected yet."}
            </p>
          ) : (
            <ul style={s.list}>
              {maneuvers.map((m) => (
                <ManeuverRow key={m.id} m={m} onSelect={setSelectedId} />
              ))}
            </ul>
          )}
        </>
      )}
    </CollapsiblePanel>
  );
};

export default ManeuverPanel;
