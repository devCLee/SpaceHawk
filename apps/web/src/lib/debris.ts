// Server-only: load tracked debris (live engine, else a direct CelesTrak pull,
// else the bundled snapshot) and compute per-object collision risk.
//
// Mirrors lib/catalog.ts's resilient-fallback philosophy so the debris layer
// always has data: the live engine /debris is preferred (it has DISCOS-enriched
// RCS + the screening loop's real Pc), then a direct server-side fetch of the
// CelesTrak debris fragmentation groups (server→server, so the browser's strict
// `connect-src 'self'` CSP doesn't apply), then a committed snapshot for
// offline/CI. Imports the snapshot JSON, so this file must only be pulled into
// server route handlers — never a client component.

import debrisData from "@/data/debris.json";
import {
  fetchDebris,
  type Debris,
  type DebrisRiskSummary,
} from "@/lib/orbital-engine";
import { deriveApsis } from "@/app/utils/sgp4FromTle";
import {
  circularSpeedKmS,
  riskLevelForScore,
  riskScore,
} from "@/app/data/debrisRisk";

const CELESTRAK_GP_URL = "https://celestrak.org/NORAD/elements/gp.php";

// The three major fragmentation clouds (~1,150 tracked objects together; ≫200).
// Matches the engine's `celestrak_debris_groups` default.
const DEBRIS_GROUPS = [
  "fengyun-1c-debris",
  "cosmos-2251-debris",
  "iridium-33-debris",
];

// Below this the engine/CelesTrak result is treated as degenerate (unseeded DB,
// blocked network) and we fall through to the next source.
const MIN_LIVE_DEBRIS = 20;

/** Raw debris record — the bundled-snapshot shape + what the TLE parse yields. */
interface DebrisRecord {
  OBJECT_NAME: string;
  OBJECT_ID?: string | null;
  NORAD_CAT_ID?: number | null;
  COUNTRY_CODE?: string | null;
  RCS_SIZE?: string | null;
  TLE_LINE0?: string | null;
  TLE_LINE1: string;
  TLE_LINE2: string;
}

/** USOID for a debris object, matching the engine's make_usoid (CAT precedence). */
function usoidFor(norad: number | null, name: string): string {
  return norad != null ? `SH:CAT:${String(norad).padStart(9, "0")}` : name;
}

/** Compute orbital params + risk for a raw debris record (TLE-only path). */
function toDebris(rec: DebrisRecord): Debris | null {
  if (!rec.TLE_LINE1 || !rec.TLE_LINE2) return null;
  const apsis = deriveApsis(rec.TLE_LINE1, rec.TLE_LINE2);
  if (apsis === null) return null;
  const meanAlt = apsis.meanAltitudeKm;
  const speed = circularSpeedKmS(meanAlt);
  const score = riskScore(meanAlt, speed, rec.RCS_SIZE);
  const norad =
    rec.NORAD_CAT_ID ?? (Number.parseInt(rec.TLE_LINE1.slice(2, 7), 10) || null);
  return {
    object_id: rec.OBJECT_ID ?? usoidFor(norad, rec.OBJECT_NAME),
    norad_cat_id: norad,
    object_name: rec.OBJECT_NAME,
    country_code: rec.COUNTRY_CODE ?? null,
    rcs_size: rec.RCS_SIZE ?? null,
    inclination: apsis.inclinationDeg,
    eccentricity: apsis.eccentricity,
    period_min: apsis.periodMin,
    apoapsis_km: apsis.apogeeKm,
    periapsis_km: apsis.perigeeKm,
    mean_altitude_km: meanAlt,
    speed_km_s: speed,
    risk_score: score,
    risk_level: riskLevelForScore(score),
    tle_line0: rec.TLE_LINE0 ?? rec.OBJECT_NAME,
    tle_line1: rec.TLE_LINE1,
    tle_line2: rec.TLE_LINE2,
  };
}

/** Parse a CelesTrak 3-line TLE export into raw records (one per 3 lines). */
function parseTleText(text: string): DebrisRecord[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trimEnd())
    .filter((l) => l.length > 0);
  const out: DebrisRecord[] = [];
  for (let i = 0; i + 2 < lines.length; i += 3) {
    const l0 = lines[i];
    const l1 = lines[i + 1];
    const l2 = lines[i + 2];
    if (!l1?.startsWith("1 ") || !l2?.startsWith("2 ")) continue;
    out.push({
      OBJECT_NAME: l0.replace(/^0 /, "").trim(),
      NORAD_CAT_ID: Number.parseInt(l1.slice(2, 7), 10) || null,
      TLE_LINE0: l0,
      TLE_LINE1: l1,
      TLE_LINE2: l2,
    });
  }
  return out;
}

/** Direct server-side fetch of the CelesTrak debris groups (one TLE pull each). */
async function fetchCelestrakDebris(): Promise<Debris[]> {
  const out: Debris[] = [];
  for (const group of DEBRIS_GROUPS) {
    try {
      const res = await fetch(
        `${CELESTRAK_GP_URL}?GROUP=${group}&FORMAT=tle`,
        { cache: "no-store" }
      );
      if (!res.ok) continue; // skip a throttled/failed group, keep the rest
      for (const rec of parseTleText(await res.text())) {
        const d = toDebris(rec);
        if (d !== null) out.push(d);
      }
    } catch {
      /* skip this group */
    }
  }
  return out;
}

// Committed snapshot of the debris groups (built by scripts/build-debris-snapshot.mjs)
// — the offline/CI fallback. Risk is computed here so the snapshot stays compact.
const fallbackDebris: Debris[] = (debrisData as DebrisRecord[])
  .map(toDebris)
  .filter((d): d is Debris => d !== null);

/**
 * The tracked-debris population with risk: the live engine when healthy, else a
 * direct CelesTrak pull, else the bundled snapshot. Never throws — the layer
 * always gets data.
 */
export async function loadDebris(): Promise<Debris[]> {
  try {
    const live = await fetchDebris();
    if (live !== null && live.length >= MIN_LIVE_DEBRIS) return live;
  } catch {
    /* fall through */
  }
  try {
    const celestrak = await fetchCelestrakDebris();
    if (celestrak.length >= MIN_LIVE_DEBRIS) return celestrak;
  } catch {
    /* fall through */
  }
  return fallbackDebris;
}

const RISK_LEVELS = ["Critical", "High", "Medium", "Low"];

/**
 * Population risk analysis computed in-process from a debris set — the offline
 * fallback for `/api/debris/risk` when the engine (which also returns screened
 * conjunctions) is unavailable. Counts per risk level + a debris-density-by-100km
 * -shell profile; `conjunctions` stays empty (real Pc needs the screening engine).
 */
export function summarizeDebrisRisk(debris: Debris[]): DebrisRiskSummary {
  const byLevel: Record<string, number> = Object.fromEntries(
    RISK_LEVELS.map((l) => [l, 0])
  );
  const shells = new Map<number, number>();
  for (const d of debris) {
    byLevel[d.risk_level] = (byLevel[d.risk_level] ?? 0) + 1;
    if (d.mean_altitude_km !== null) {
      const band = Math.floor(d.mean_altitude_km / 100) * 100;
      shells.set(band, (shells.get(band) ?? 0) + 1);
    }
  }
  const density = [...shells.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([altitude_km, count]) => ({ altitude_km, count }));
  return {
    available: true,
    total: debris.length,
    by_level: byLevel,
    density_by_shell: density,
    conjunctions: [],
  };
}
