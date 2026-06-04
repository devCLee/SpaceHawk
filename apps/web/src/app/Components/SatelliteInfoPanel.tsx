"use client";

// Per-satellite info sidebar (#9h). Opens when an object is selected on the
// globe (selected-satellite context); shows four field groups:
//   - Current Position   (lat / lon / altitude)
//   - Orbital Velocity   (speed magnitude + ECI components)
//   - Orbital Parameters (inclination, eccentricity, period, apoapsis/perigee)
//   - Detailed Elements  (RAAN, arg of perigee, mean anomaly, epoch)
//
// Static orbital data comes from the engine via the BFF (`/api/catalog/{id}`);
// the live position/velocity readout is propagated client-side from the TLE
// (display only — dev-plan §4.2). Field layout adapted from project-lynx2's
// SatelliteInfoPanel.tsx (MIT, same stack).

import React from "react";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { useCatalogView } from "../context/CatalogViewContext";
import { runSgp4State, type Sgp4State } from "../utils/sgp4FromTle";
import type { ObjectDetail } from "@/lib/orbital-engine";

/** Live position/velocity refresh cadence. */
const LIVE_UPDATE_MS = 1000;

function fmt(value: number | null | undefined, digits = 3, unit = ""): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}${unit ? ` ${unit}` : ""}`;
}

const Row: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div style={styles.row}>
    <span style={styles.rowLabel}>{label}</span>
    <span style={styles.rowValue}>{value}</span>
  </div>
);

const Group: React.FC<{ title: string; children: React.ReactNode }> = ({
  title,
  children,
}) => (
  <section style={styles.group}>
    <h3 style={styles.groupTitle}>{title}</h3>
    {children}
  </section>
);

export const SatelliteInfoPanel: React.FunctionComponent = () => {
  const { selectedId, setSelectedId } = useSelectedSatellite();
  const { isWatched, toggleWatch } = useCatalogView();
  const [detail, setDetail] = React.useState<ObjectDetail | null>(null);
  const [status, setStatus] = React.useState<
    "idle" | "loading" | "error" | "ready"
  >("idle");
  const [live, setLive] = React.useState<Sgp4State | null>(null);

  // Fetch the selected object's detail whenever the selection changes.
  React.useEffect(() => {
    if (selectedId === null) {
      setDetail(null);
      setStatus("idle");
      return;
    }
    const controller = new AbortController();
    setStatus("loading");
    setDetail(null);
    setLive(null);
    fetch(`/api/catalog/${encodeURIComponent(selectedId)}`, {
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`detail fetch failed: ${res.status}`);
        return res.json() as Promise<ObjectDetail>;
      })
      .then((d) => {
        setDetail(d);
        setStatus("ready");
      })
      .catch((err) => {
        if (err.name === "AbortError") return;
        setStatus("error");
      });
    return () => controller.abort();
  }, [selectedId]);

  // Propagate the live position/velocity from the TLE on a timer.
  React.useEffect(() => {
    const line1 = detail?.tle_line1;
    const line2 = detail?.tle_line2;
    if (!line1 || !line2) {
      setLive(null);
      return;
    }
    const tick = () => setLive(runSgp4State(line1, line2, new Date()));
    tick();
    const handle = window.setInterval(tick, LIVE_UPDATE_MS);
    return () => window.clearInterval(handle);
  }, [detail?.tle_line1, detail?.tle_line2]);

  if (selectedId === null) return null;

  return (
    <aside style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.headerTitle}>
          {detail?.object_name ?? "Loading…"}
        </span>
        <div style={{ display: "flex", gap: 4 }}>
          <button
            type="button"
            aria-label={
              isWatched(selectedId) ? "Remove from watchlist" : "Add to watchlist"
            }
            onClick={() => toggleWatch(selectedId)}
            style={{
              ...styles.closeButton,
              color: isWatched(selectedId) ? "#ffa94d" : "#9aa7b4",
            }}
          >
            {isWatched(selectedId) ? "★" : "☆"}
          </button>
          <button
            type="button"
            aria-label="Close info panel"
            onClick={() => setSelectedId(null)}
            style={styles.closeButton}
          >
            ✕
          </button>
        </div>
      </div>

      {status === "loading" && <p style={styles.muted}>Loading object detail…</p>}
      {status === "error" && (
        <p style={styles.error}>Couldn’t load object detail.</p>
      )}

      {status === "ready" && detail && (
        <>
          <Group title="Identity">
            <Row label="NORAD ID" value={detail.norad_cat_id?.toString() ?? "—"} />
            <Row label="Int'l designator" value={detail.intl_designator ?? "—"} />
            <Row label="Type" value={detail.object_type ?? "—"} />
            <Row label="Country" value={detail.country_code ?? "—"} />
          </Group>

          <Group title="Current Position">
            <Row label="Latitude" value={fmt(live?.lat, 3, "°")} />
            <Row label="Longitude" value={fmt(live?.lng, 3, "°")} />
            <Row label="Altitude" value={fmt(live?.altKm, 1, "km")} />
          </Group>

          <Group title="Orbital Velocity">
            <Row label="Speed" value={fmt(live?.speedKmS, 3, "km/s")} />
            <Row label="Vx" value={fmt(live?.velocity.x, 3, "km/s")} />
            <Row label="Vy" value={fmt(live?.velocity.y, 3, "km/s")} />
            <Row label="Vz" value={fmt(live?.velocity.z, 3, "km/s")} />
          </Group>

          <Group title="Orbital Parameters">
            <Row label="Inclination" value={fmt(detail.inclination, 3, "°")} />
            <Row label="Eccentricity" value={fmt(detail.eccentricity, 6)} />
            <Row label="Period" value={fmt(detail.period_min, 2, "min")} />
            <Row label="Apoapsis" value={fmt(detail.apoapsis_km, 1, "km")} />
            <Row label="Periapsis" value={fmt(detail.periapsis_km, 1, "km")} />
          </Group>

          <Group title="Detailed Orbital Elements">
            <Row label="RAAN" value={fmt(detail.ra_of_asc_node, 3, "°")} />
            <Row label="Arg of perigee" value={fmt(detail.arg_of_pericenter, 3, "°")} />
            <Row label="Mean anomaly" value={fmt(detail.mean_anomaly, 3, "°")} />
            <Row label="Mean motion" value={fmt(detail.mean_motion, 6, "rev/day")} />
            <Row label="Semi-major axis" value={fmt(detail.semimajor_axis_km, 1, "km")} />
            <Row
              label="Epoch"
              value={detail.epoch ? new Date(detail.epoch).toISOString() : "—"}
            />
          </Group>
        </>
      )}
    </aside>
  );
};

export default SatelliteInfoPanel;

const styles: Record<string, React.CSSProperties> = {
  panel: {
    position: "absolute",
    top: 0,
    right: 0,
    zIndex: 20,
    width: 320,
    maxHeight: "calc(100vh - 56px)",
    overflowY: "auto",
    padding: "12px 16px",
    background: "rgba(8, 12, 20, 0.92)",
    borderLeft: "1px solid rgba(255,255,255,0.12)",
    color: "#e6edf3",
    fontSize: 13,
    fontFamily: "system-ui, sans-serif",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 8,
    gap: 8,
  },
  headerTitle: { fontSize: 15, fontWeight: 600, lineHeight: 1.2 },
  closeButton: {
    border: "none",
    background: "transparent",
    color: "#9aa7b4",
    fontSize: 14,
    cursor: "pointer",
    padding: 4,
  },
  group: { marginTop: 12 },
  groupTitle: {
    margin: "0 0 4px",
    fontSize: 11,
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    color: "#7d8da0",
  },
  row: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    padding: "2px 0",
  },
  rowLabel: { color: "#9aa7b4" },
  rowValue: { fontVariantNumeric: "tabular-nums", textAlign: "right" },
  muted: { color: "#7d8da0" },
  error: { color: "#ff6b6b" },
};
