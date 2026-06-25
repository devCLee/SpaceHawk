"use client";

// Visualization options (#viz): colour the catalogue by orbit regime or object
// class (OpenSSA / KeepTrack-style) and toggle whole categories on/off on the
// globe. Doubles as the colour legend. Drives the shared catalog-view state; the
// globe recolours and hides accordingly.

import React from "react";
import CollapsiblePanel from "./CollapsiblePanel";
import { useCatalogView } from "../context/CatalogViewContext";
import {
  categoriesFor,
  categoryColor,
  type ColorMode,
} from "../data/visualization";
import { objectTypeLabel } from "@/lib/i18n/enums";
import * as s from "./panelStyles";
import { t } from "@/lib/i18n/t";

const MODES: ColorMode[] = ["regime", "type"];

function modeButton(active: boolean): React.CSSProperties {
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

function toggleRow(active: boolean): React.CSSProperties {
  return {
    ...s.listItem,
    width: "100%",
    boxSizing: "border-box",
    border: "none",
    textAlign: "left",
    font: "inherit",
    color: "inherit",
    background: active ? "rgba(0,180,220,0.18)" : "rgba(0,0,0,0.4)",
  };
}

export const VisualizationPanel: React.FunctionComponent = () => {
  const {
    colorMode,
    setColorMode,
    isCategoryHidden,
    toggleCategory,
    watchlistOnly,
    setWatchlistOnly,
  } = useCatalogView();

  // Regime codes (LEO/MEO/GEO/HEO) are not translated (messages.ts policy);
  // object-class values are localized via the shared enum label map.
  const label = (key: string) =>
    colorMode === "type" ? objectTypeLabel(key) : key;

  return (
    <CollapsiblePanel title={t("viz.title")} defaultOpen>
      <div style={s.label}>{t("viz.colorBy")}</div>
      <div style={{ display: "flex", gap: 6 }}>
        {MODES.map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={colorMode === m}
            onClick={() => setColorMode(m)}
            style={modeButton(colorMode === m)}
          >
            {m === "regime" ? t("viz.mode.regime") : t("viz.mode.type")}
          </button>
        ))}
      </div>
      <button
        type="button"
        aria-pressed={watchlistOnly}
        onClick={() => setWatchlistOnly(!watchlistOnly)}
        style={toggleRow(watchlistOnly)}
      >
        <span>{t("viz.watchlistOnly")}</span>
        <span style={s.muted}>{watchlistOnly ? "◉" : "◯"}</span>
      </button>
      <ul style={s.list}>
        {categoriesFor(colorMode).map((key) => {
          const hidden = isCategoryHidden(key);
          return (
            <li
              key={key}
              style={{ ...s.listItem, opacity: hidden ? 0.4 : 1 }}
              onClick={() => toggleCategory(key)}
              role="button"
              aria-pressed={!hidden}
              aria-label={`${label(key)} — ${
                hidden ? t("viz.show") : t("viz.hide")
              }`}
            >
              <span
                style={{ display: "flex", alignItems: "center", gap: 8 }}
              >
                <span style={swatch(categoryColor(colorMode, key))} />
                <span>{label(key)}</span>
              </span>
              <span style={s.muted}>{hidden ? "◯" : "◉"}</span>
            </li>
          );
        })}
      </ul>
    </CollapsiblePanel>
  );
};

export default VisualizationPanel;
