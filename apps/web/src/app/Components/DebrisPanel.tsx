"use client";

// Debris layer controls + collision-risk analysis (#debris). Toggles the
// risk-coloured debris layer / heatmap on the globe; shows a per-risk legend with
// live counts + show/hide, a debris-density-by-altitude profile (the classic ODPO
// LEO profile, peaking ~800-1000 km), the screened collision-probability
// conjunctions (real Pc from the engine), and a high-risk drill-down list
// (selecting a row focuses the object on the globe). Mirrors VisualizationPanel /
// CollisionsPanel conventions.

import React from "react";
import CollapsiblePanel from "./CollapsiblePanel";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { useDebrisLayer } from "../context/DebrisLayerContext";
import { useDebris, useDebrisRisk } from "@/lib/api/useDebris";
import DebrisHeatmap2D from "./DebrisHeatmap2D";
import { RISK_ORDER, riskColor, RISK_LABEL_KEY } from "../data/debrisRisk";
import * as s from "./panelStyles";
import { t } from "@/lib/i18n/t";

const TOP_RISK_COUNT = 12;

function swatch(color: string): React.CSSProperties {
  return {
    width: 12,
    height: 12,
    borderRadius: 3,
    background: color,
    border: "1px solid rgba(255,255,255,0.25)",
    flexShrink: 0,
  };
}

function toggleButton(active: boolean): React.CSSProperties {
  return {
    ...s.input,
    flex: 1,
    width: "auto",
    cursor: "pointer",
    background: active ? "rgba(0,180,220,0.22)" : "rgba(0,0,0,0.4)",
    borderColor: active ? "rgba(0,180,220,0.6)" : "rgba(255,255,255,0.18)",
    fontWeight: active ? 600 : 400,
  };
}

export const DebrisPanel: React.FunctionComponent = () => {
  const { setSelectedId } = useSelectedSatellite();
  const {
    visible,
    toggleVisible,
    heatmap,
    setHeatmap,
    isRiskHidden,
    toggleRisk,
  } = useDebrisLayer();

  const { data: debris, isLoading, isError } = useDebris();
  const { data: risk } = useDebrisRisk();

  const byLevel = risk?.by_level ?? {};
  const total = debris?.length ?? risk?.total ?? 0;
  const conjunctions = risk?.conjunctions ?? [];
  const density = React.useMemo(() => risk?.density_by_shell ?? [], [risk]);
  const maxShell = React.useMemo(
    () => density.reduce((m, b) => Math.max(m, b.count), 0),
    [density]
  );

  const topRisk = React.useMemo(
    () =>
      [...(debris ?? [])]
        .sort((a, b) => b.risk_score - a.risk_score)
        .slice(0, TOP_RISK_COUNT),
    [debris]
  );

  return (
    <CollapsiblePanel title={t("debris.title")}>
      <div style={{ display: "flex", gap: 6 }}>
        <button
          type="button"
          aria-pressed={visible}
          onClick={toggleVisible}
          style={toggleButton(visible)}
          className="break-keep"
        >
          {visible ? t("debris.layer.hide") : t("debris.layer.show")}
        </button>
        <button
          type="button"
          aria-pressed={heatmap}
          onClick={() => setHeatmap(!heatmap)}
          style={toggleButton(heatmap)}
        >
          {t("debris.heatmap")}
        </button>
      </div>

      {/* 2D geographic density heatmap (renders inline when toggled on). */}
      <DebrisHeatmap2D />

      {isLoading && <p style={s.muted}>{t("debris.loading")}</p>}
      {isError && <p style={s.error}>{t("debris.error")}</p>}

      {!isLoading && !isError && (
        <>
          <div style={s.muted}>{t("debris.count", { n: total })}</div>

          {/* Risk legend + counts (click a tier to show/hide it). */}
          <div style={s.label}>{t("debris.legend")}</div>
          <ul style={s.list}>
            {RISK_ORDER.map((level) => {
              const hidden = isRiskHidden(level);
              return (
                <li
                  key={level}
                  style={{ ...s.listItem, opacity: hidden ? 0.4 : 1 }}
                  onClick={() => toggleRisk(level)}
                  role="button"
                  aria-pressed={!hidden}
                  aria-label={t(RISK_LABEL_KEY[level])}
                >
                  <span
                    style={{ display: "flex", alignItems: "center", gap: 8 }}
                  >
                    <span style={swatch(riskColor(level))} />
                    <span>{t(RISK_LABEL_KEY[level])}</span>
                  </span>
                  <span style={s.muted}>{byLevel[level] ?? 0}</span>
                </li>
              );
            })}
          </ul>

          {/* Debris-density-by-100km-shell profile (ODPO LEO profile). */}
          {density.length > 0 && (
            <>
              <div style={s.label}>{t("debris.density.title")}</div>
              <div
                style={{ display: "flex", flexDirection: "column", gap: 2 }}
              >
                {density.map((b) => (
                  <div
                    key={b.altitude_km}
                    style={{ display: "flex", alignItems: "center", gap: 6 }}
                  >
                    {/* Fixed-width, non-shrinking label so every altitude is
                        right-aligned to the same edge regardless of bar length. */}
                    <span
                      style={{
                        ...s.muted,
                        width: 56,
                        flexShrink: 0,
                        fontSize: 11,
                        textAlign: "right",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {b.altitude_km} km
                    </span>
                    {/* Bar + count share the remaining space, so the bar stays
                        proportional (its % is of this track) instead of overflowing
                        the row and squeezing the label. */}
                    <span
                      style={{
                        flex: 1,
                        minWidth: 0,
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      <span
                        style={{
                          height: 8,
                          borderRadius: 2,
                          background: "rgba(0,180,220,0.6)",
                          width: `${maxShell ? (b.count / maxShell) * 100 : 0}%`,
                          minWidth: 2,
                        }}
                      />
                      <span style={{ ...s.muted, fontSize: 11, flexShrink: 0 }}>
                        {b.count}
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Screened collision conjunctions (real Pc from the engine). */}
          <div style={s.label}>{t("debris.collisions.title")}</div>
          {conjunctions.length === 0 ? (
            <p style={s.muted}>
              {risk?.available
                ? t("debris.collisions.none")
                : t("debris.collisions.offline")}
            </p>
          ) : (
            <div style={s.muted}>
              {t("debris.collisions.count", { n: conjunctions.length })}
            </div>
          )}

          {/* High-risk drill-down: click focuses the object on the globe. */}
          {topRisk.length > 0 && (
            <>
              <div style={s.label}>{t("debris.topRisk.title")}</div>
              <ul style={s.list}>
                {topRisk.map((d) => (
                  <li
                    key={d.object_id}
                    style={s.listItem}
                    onClick={() => setSelectedId(`debris:${d.object_id}`)}
                  >
                    <span
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        minWidth: 0,
                      }}
                    >
                      <span style={swatch(riskColor(d.risk_level))} />
                      <span
                        style={{
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {d.object_name}
                      </span>
                    </span>
                    <span style={s.muted}>{d.risk_score.toFixed(0)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          <p style={{ ...s.muted, fontSize: 11 }}>{t("debris.source")}</p>
        </>
      )}
    </CollapsiblePanel>
  );
};

export default DebrisPanel;
