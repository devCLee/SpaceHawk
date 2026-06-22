// Debris collision-risk model (client + server safe). A 1:1 mirror of the engine
// model in services/orbital-engine/orbital_engine/debris_risk.py so the three
// data paths — live engine, direct-CelesTrak fallback, bundled snapshot — all
// produce the same risk score/level. The score is a relative-risk index (0-100),
// NOT a physical probability of collision (that comes from the engine's SGP4
// screening / estimate_pc, surfaced via /api/debris/risk conjunctions).
//
// score = 100 · Dn · Vn · Sn
//   Dn  altitude-shell debris spatial-density (peaks ~750-1000 km, ~1400 km)
//   Vn  orbital-speed factor (impact-energy proxy)
//   Sn  RCS size-class factor

import {
  RISK_COLORS,
  RISK_ORDER,
  riskColor,
  type DebrisRiskLevel,
} from "./visualization";
import type { MessageKey } from "@/lib/i18n/t";

export { RISK_COLORS, RISK_ORDER, riskColor, type DebrisRiskLevel };

/** 2D-heatmap intensity weight per risk level (Critical densest → Low lightest). */
export const RISK_WEIGHT: Record<DebrisRiskLevel, number> = {
  Critical: 1.0,
  High: 0.7,
  Medium: 0.4,
  Low: 0.2,
};

/** i18n keys for the risk-level labels (the level CODE stays English/raw). Lives
 *  here (not in a component) so panels + the heatmap share it without a cycle. */
export const RISK_LABEL_KEY: Record<DebrisRiskLevel, MessageKey> = {
  Critical: "debris.risk.Critical",
  High: "debris.risk.High",
  Medium: "debris.risk.Medium",
  Low: "debris.risk.Low",
};

const MU_EARTH = 398600.4418; // km^3/s^2
const R_EARTH = 6378.137; // km

/** Debris spatial-density factor in [0,1] for a circular-equivalent altitude. */
export function densityFactor(meanAltitudeKm: number): number {
  const h = meanAltitudeKm;
  if (h >= 750 && h <= 1000) return 1.0; // primary LEO debris peak
  if (h >= 1300 && h <= 1500) return 0.8; // secondary ~1400 km peak
  if ((h >= 600 && h < 750) || (h > 1000 && h < 1300)) return 0.6;
  if ((h >= 500 && h < 600) || (h > 1500 && h <= 2000)) return 0.35;
  if (h >= 350 && h < 500) return 0.2; // drag clears it fast
  if (h > 2000) return 0.15; // MEO / above the LEO belt
  return 0.1; // < 350 km (decaying)
}

/** Orbital-speed factor in [0,1] (≈1 in dense LEO, lower in MEO/GEO). */
export function velocityFactor(speedKmS: number): number {
  return Math.max(0, Math.min(1, speedKmS / 8));
}

/** RCS size-class factor; UNKNOWN (the CelesTrak-GP common case) is the midpoint. */
export function sizeFactor(rcsSize: string | null | undefined): number {
  switch ((rcsSize ?? "").toUpperCase()) {
    case "LARGE":
      return 1.0;
    case "MEDIUM":
      return 0.6;
    case "SMALL":
      return 0.3;
    default:
      return 0.5;
  }
}

/** Circular orbital speed [km/s] at a mean altitude (vis-viva, e≈0). */
export function circularSpeedKmS(meanAltitudeKm: number): number {
  return Math.sqrt(MU_EARTH / (meanAltitudeKm + R_EARTH));
}

/** 0-100 risk index = 100 · Dn · Vn · Sn (rounded to 0.1). */
export function riskScore(
  meanAltitudeKm: number,
  speedKmS: number,
  rcsSize: string | null | undefined
): number {
  const score =
    100 *
    densityFactor(meanAltitudeKm) *
    velocityFactor(speedKmS) *
    sizeFactor(rcsSize);
  return Math.round(score * 10) / 10;
}

/** Bucket a 0-100 score into Critical/High/Medium/Low. */
export function riskLevelForScore(score: number): DebrisRiskLevel {
  if (score >= 70) return "Critical";
  if (score >= 45) return "High";
  if (score >= 20) return "Medium";
  return "Low";
}
