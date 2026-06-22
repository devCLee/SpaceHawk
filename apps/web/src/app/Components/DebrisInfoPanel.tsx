"use client";

// Per-debris detail popup (#debris). Opens when a `debris:`-prefixed object is
// selected on the globe (or from the DebrisPanel list); shows its risk
// score/level, orbital parameters (derived from the TLE), and — when the engine
// has screened it — the real probability-of-collision of its worst conjunction.
// Distinct from SatelliteInfoPanel (which renders for catalog objects); the two
// share the same anchor and never show together (selection is one id).

import React from "react";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { useDebris, useDebrisRisk } from "@/lib/api/useDebris";
import {
  riskColor,
  RISK_LABEL_KEY,
  type DebrisRiskLevel,
} from "../data/debrisRisk";
import { t } from "@/lib/i18n/t";

const DEBRIS_PREFIX = "debris:";

function fmt(value: number | null | undefined, digits = 2, unit = ""): string {
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

export const DebrisInfoPanel: React.FunctionComponent = () => {
  const { selectedId, setSelectedId } = useSelectedSatellite();
  const { data: debris } = useDebris();
  const { data: risk } = useDebrisRisk();

  const objectId = selectedId?.startsWith(DEBRIS_PREFIX)
    ? selectedId.slice(DEBRIS_PREFIX.length)
    : null;

  const item = React.useMemo(
    () =>
      objectId && debris
        ? debris.find((d) => d.object_id === objectId) ?? null
        : null,
    [objectId, debris]
  );

  // The worst screened conjunction this debris participates in (real Pc), if any.
  const conjunction = React.useMemo(() => {
    if (!objectId || !risk?.conjunctions) return null;
    return (
      risk.conjunctions.find(
        (c) =>
          c.primary_object_id === objectId ||
          c.secondary_object_id === objectId
      ) ?? null
    );
  }, [objectId, risk]);

  if (objectId === null) return null;

  const level = (item?.risk_level as DebrisRiskLevel) ?? "Low";

  return (
    <aside style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.headerTitle}>{item?.object_name ?? objectId}</span>
        <button
          type="button"
          aria-label={t("sat.closePanel")}
          onClick={() => setSelectedId(null)}
          style={styles.closeButton}
        >
          ✕
        </button>
      </div>

      {!item ? (
        <p style={styles.muted}>{t("debris.loading")}</p>
      ) : (
        <>
          <Group title={t("debris.title")}>
            <div style={styles.row}>
              <span style={styles.rowLabel}>{t("debris.level")}</span>
              <span
                style={{
                  ...styles.rowValue,
                  color: riskColor(level),
                  fontWeight: 600,
                }}
              >
                {t(RISK_LABEL_KEY[level])}
              </span>
            </div>
            <Row label={t("debris.score")} value={item.risk_score.toFixed(0)} />
            <Row
              label="NORAD ID"
              value={item.norad_cat_id?.toString() ?? "—"}
            />
            <Row label={t("sat.row.country")} value={item.country_code ?? "—"} />
            <Row label={t("debris.rcs")} value={item.rcs_size ?? "—"} />
          </Group>

          <Group title={t("sat.group.params")}>
            <Row
              label={t("debris.meanAltitude")}
              value={fmt(item.mean_altitude_km, 0, "km")}
            />
            <Row
              label={t("sat.row.inclination")}
              value={fmt(item.inclination, 2, "°")}
            />
            <Row
              label={t("sat.row.eccentricity")}
              value={fmt(item.eccentricity, 5)}
            />
            <Row
              label={t("sat.row.period")}
              value={fmt(item.period_min, 1, "min")}
            />
            <Row
              label={t("sat.row.apoapsis")}
              value={fmt(item.apoapsis_km, 0, "km")}
            />
            <Row
              label={t("sat.row.periapsis")}
              value={fmt(item.periapsis_km, 0, "km")}
            />
          </Group>

          <Group title={t("debris.collisions.title")}>
            {conjunction ? (
              <>
                <Row
                  label="Pc"
                  value={
                    conjunction.probability != null
                      ? conjunction.probability.toExponential(1)
                      : "—"
                  }
                />
                <Row
                  label="↔"
                  value={fmt(conjunction.miss_distance_km, 2, "km")}
                />
              </>
            ) : (
              <p style={styles.muted}>
                {risk?.available
                  ? t("debris.collisions.none")
                  : t("debris.collisions.offline")}
              </p>
            )}
          </Group>
        </>
      )}
    </aside>
  );
};

export default DebrisInfoPanel;

const styles: Record<string, React.CSSProperties> = {
  panel: {
    position: "absolute",
    top: 160,
    right: 12,
    zIndex: 20,
    width: 320,
    maxHeight: "calc(100vh - 172px)",
    overflowY: "auto",
    overscrollBehavior: "contain",
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
};
