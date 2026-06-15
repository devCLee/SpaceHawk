// Globe colour-coding vocabulary (#viz): the two axes a user can colour the
// catalogue by — object class (KeepTrack-style) and orbit regime (OpenSSA-style)
// — plus the palettes and the object-class classifier. The palettes are plain
// hex so they are the single source of truth for BOTH the Cesium points
// (parsed via Cesium.Color.fromCssColorString) and the panel's CSS swatches.

import type { OrbitRegime } from "../utils/sgp4FromTle";

export type ColorMode = "type" | "regime";

/** The four object classes we colour by (CCSDS/SATCAT object_type, bucketed). */
export type ObjectCategory = "PAYLOAD" | "ROCKET BODY" | "DEBRIS" | "UNKNOWN";

// Object-class palette (KeepTrack-style): payload / rocket body / debris.
export const TYPE_COLORS: Record<ObjectCategory, string> = {
  PAYLOAD: "#34d399", // green
  "ROCKET BODY": "#60a5fa", // blue
  DEBRIS: "#f87171", // red
  UNKNOWN: "#9ca3af", // gray
};
export const TYPE_ORDER: ObjectCategory[] = [
  "PAYLOAD",
  "ROCKET BODY",
  "DEBRIS",
  "UNKNOWN",
];

// Orbit-regime palette (OpenSSA / Lynx-style): LEO / MEO / GEO / HEO.
export const REGIME_COLORS: Record<OrbitRegime, string> = {
  LEO: "#34d399", // green
  MEO: "#38bdf8", // cyan-blue
  GEO: "#fbbf24", // amber
  HEO: "#c084fc", // purple
};
export const REGIME_ORDER: OrbitRegime[] = ["LEO", "MEO", "GEO", "HEO"];

/** Colour for an object with no resolvable category (e.g. an unparseable TLE). */
export const CATEGORY_FALLBACK_COLOR = "#9ca3af";

/** The category keys shown in the legend (and toggled for visibility) per mode. */
export function categoriesFor(mode: ColorMode): string[] {
  return mode === "type" ? TYPE_ORDER : REGIME_ORDER;
}

/** Hex colour for a category key under the active mode (fallback if unknown). */
export function categoryColor(mode: ColorMode, key: string): string {
  if (mode === "type") {
    return TYPE_COLORS[key as ObjectCategory] ?? CATEGORY_FALLBACK_COLOR;
  }
  return REGIME_COLORS[key as OrbitRegime] ?? CATEGORY_FALLBACK_COLOR;
}

/**
 * Classify a catalogue object into one of the four colour classes. Prefers the
 * engine's authoritative `object_type`; falls back to the public CelesTrak name
 * convention (`… R/B` = rocket body, `… DEB` = debris) so the active-only
 * bundled snapshot — which omits object_type — still colours correctly. The
 * heuristic is derived from the public CelesTrak naming convention, independent
 * of keeptrack's AGPL dataset (LICENSE-DECISION-RECORD §4.7).
 */
export function classifyObjectType(
  name: string | null | undefined,
  engineType?: string | null
): ObjectCategory {
  const t = engineType?.toUpperCase().trim();
  if (t === "PAYLOAD" || t === "ROCKET BODY" || t === "DEBRIS") return t;
  if (t === "UNKNOWN" || t === "TBA") return "UNKNOWN";

  const n = (name ?? "").toUpperCase();
  if (/R\/B/.test(n)) return "ROCKET BODY";
  if (/\bDEB\b|DEBRIS|COOLANT|SHROUD|WESTFORD NEEDLES/.test(n)) return "DEBRIS";
  if (!name) return "UNKNOWN";
  return "PAYLOAD";
}
