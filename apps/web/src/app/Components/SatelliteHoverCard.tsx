"use client";

// Hover card (#9i): a compact read-out shown when the cursor rests on a catalog
// point on the globe. Surfaces the essentials already carried on the rendered
// point (name, owner + flag, catalog id, object class, orbit regime,
// constellation) so the user can scan objects without clicking through to the
// full SatelliteInfoPanel. Position/identity come straight off the point record
// — no /api/catalog round-trip — so it stays cheap on a high-frequency mousemove.

import React from "react";
import * as Flags from "country-flag-icons/react/3x2";
import { countryName, countryISO } from "../data/countries";
import { t } from "@/lib/i18n/t";

/** Identity snapshot the globe hands the card on hover (canvas-relative x/y). */
export interface SatelliteHoverInfo {
  id: string;
  name: string;
  countryCode: string | null;
  category: string;
  regime: string | null;
  constellation: string | null;
  x: number;
  y: number;
}

type FlagComponent = React.FC<React.SVGProps<SVGSVGElement> & { title?: string }>;

/** Approximate card footprint — used only to flip the card away from the
 *  viewport edge so it never spills off-screen near the right/bottom. */
const CARD_W = 230;
const CARD_H = 150;
const CURSOR_OFFSET = 16;
const HEADER_H = 56; // globe canvas sits below the app header

const Row: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div style={styles.row}>
    <span style={styles.rowLabel}>{label}</span>
    <span style={styles.rowValue}>{value}</span>
  </div>
);

export const SatelliteHoverCard: React.FunctionComponent<{
  info: SatelliteHoverInfo | null;
}> = ({ info }) => {
  if (info === null) return null;

  const iso = countryISO(info.countryCode);
  const Flag = iso
    ? (Flags as unknown as Record<string, FlagComponent>)[iso]
    : undefined;

  // Flip horizontally/vertically when the cursor is near the right/bottom edge
  // so the card grows back toward screen centre instead of clipping.
  const vw = typeof window !== "undefined" ? window.innerWidth : 1920;
  const vh = typeof window !== "undefined" ? window.innerHeight : 1080;
  const flipX = info.x + CURSOR_OFFSET + CARD_W > vw;
  const flipY = info.y + CURSOR_OFFSET + CARD_H > vh - HEADER_H;

  const position: React.CSSProperties = {
    left: flipX ? info.x - CURSOR_OFFSET : info.x + CURSOR_OFFSET,
    top: flipY ? info.y - CURSOR_OFFSET : info.y + CURSOR_OFFSET,
    transform: `translate(${flipX ? "-100%" : "0"}, ${flipY ? "-100%" : "0"})`,
  };

  return (
    <div style={{ ...styles.card, ...position }} role="tooltip">
      <div style={styles.title}>{info.name}</div>

      <div style={styles.country}>
        {Flag ? (
          <Flag title={countryName(info.countryCode)} style={styles.flag} />
        ) : (
          <span style={styles.flagFallback} aria-hidden>
            🌐
          </span>
        )}
        <span>{countryName(info.countryCode)}</span>
      </div>

      <div style={styles.rows}>
        <Row label={t("sat.hover.id")} value={info.id} />
        <Row label={t("sat.row.type")} value={info.category} />
        <Row label={t("sat.hover.orbit")} value={info.regime ?? "—"} />
        {info.constellation && (
          <Row label={t("sat.hover.constellation")} value={info.constellation} />
        )}
      </div>
    </div>
  );
};

export default SatelliteHoverCard;

const styles: Record<string, React.CSSProperties> = {
  card: {
    position: "absolute",
    zIndex: 25,
    width: CARD_W,
    // The card tracks the cursor; never let it eat pointer events or it would
    // block the globe's own pick/hover under the card.
    pointerEvents: "none",
    padding: "10px 12px",
    background: "rgba(8, 12, 20, 0.94)",
    border: "1px solid rgba(255,255,255,0.14)",
    borderRadius: 8,
    boxShadow: "0 6px 24px rgba(0,0,0,0.45)",
    color: "#e6edf3",
    fontSize: 12,
    fontFamily: "system-ui, sans-serif",
  },
  title: {
    fontSize: 14,
    fontWeight: 600,
    lineHeight: 1.2,
    marginBottom: 6,
    wordBreak: "break-word",
  },
  country: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    marginBottom: 8,
    color: "#c4d0dc",
  },
  flag: {
    width: 18,
    height: 13,
    borderRadius: 2,
    flexShrink: 0,
    boxShadow: "0 0 0 1px rgba(255,255,255,0.12)",
  },
  flagFallback: { fontSize: 14, lineHeight: 1 },
  rows: { display: "flex", flexDirection: "column", gap: 2 },
  row: { display: "flex", justifyContent: "space-between", gap: 12 },
  rowLabel: { color: "#9aa7b4" },
  rowValue: {
    fontVariantNumeric: "tabular-nums",
    textAlign: "right",
    wordBreak: "break-word",
  },
};
