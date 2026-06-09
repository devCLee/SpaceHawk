// Snapshot-backed object detail — the per-satellite fallback for `/api/catalog/{id}`.
//
// The globe falls back to the bundled `main.json` snapshot when the engine
// catalog is unavailable / too sparse (main/page.tsx, MIN_LIVE_CATALOG). Without
// a matching fallback here, every click on a snapshot-rendered object 404s
// because the detail endpoint only reads the (possibly unseeded) engine DB. This
// closes that gap: if the engine has no record, derive what the sidebar needs
// from the snapshot's TLE so the panel still populates. Server-only (imported by
// the Node-runtime BFF route); the snapshot lacks object_type / launch_date, so
// those stay null (the panel renders "—").

import { twoline2satrec } from "satellite.js";

import mainData from "@/data/main.json";
import type { ObjectDetail } from "@/lib/orbital-engine";
import type { TleObject } from "@/app/utils/sgp4FromTle";

// WGS-72 earth radius — the constant satellite.js uses internally, so satrec's
// `a` / `alta` / `altp` (in earth radii) convert back to km consistently.
const EARTH_RADIUS_KM = 6378.135;

let snapshotIndex: Map<string, TleObject> | null = null;

/** Lazily index the bundled snapshot by OBJECT_ID for O(1) lookup. */
function getIndex(): Map<string, TleObject> {
  if (snapshotIndex) return snapshotIndex;
  const index = new Map<string, TleObject>();
  for (const entry of mainData as TleObject[]) {
    if (entry.OBJECT_ID && entry.TLE_LINE1 && entry.TLE_LINE2) {
      index.set(entry.OBJECT_ID, entry);
    }
  }
  snapshotIndex = index;
  return index;
}

const toDeg = (rad: number): number => (rad * 180) / Math.PI;

/**
 * Build the sidebar's `ObjectDetail` from a snapshot entry by deriving the
 * orbital elements from its TLE, or return null if the object isn't in the
 * snapshot (or its TLE won't parse).
 */
export function findSnapshotDetail(objectId: string): ObjectDetail | null {
  const entry = getIndex().get(objectId);
  if (!entry?.TLE_LINE1 || !entry.TLE_LINE2) return null;

  const satrec = twoline2satrec(entry.TLE_LINE1, entry.TLE_LINE2);
  if (!satrec.no || satrec.no <= 0) return null; // unparseable / degenerate TLE

  // satrec.no is rad/min; rev/day = no * (min/day) / (rad/rev).
  const meanMotionRevPerDay = (satrec.no * 1440) / (2 * Math.PI);
  // Julian date -> Unix ms: JD 2440587.5 == 1970-01-01T00:00:00Z.
  const epoch = Number.isFinite(satrec.jdsatepoch)
    ? new Date((satrec.jdsatepoch - 2440587.5) * 86400000).toISOString()
    : null;

  return {
    object_id: entry.OBJECT_ID ?? objectId,
    norad_cat_id: entry.NORAD_CAT_ID ?? null,
    intl_designator: entry.OBJECT_ID ?? null,
    object_name: entry.OBJECT_NAME ?? entry.OBJECT_ID ?? objectId,
    object_type: null, // not in the snapshot
    country_code: entry.COUNTRY_CODE ?? null,
    launch_date: null, // not in the snapshot
    epoch,
    inclination: toDeg(satrec.inclo),
    eccentricity: satrec.ecco,
    ra_of_asc_node: toDeg(satrec.nodeo),
    arg_of_pericenter: toDeg(satrec.argpo),
    mean_anomaly: toDeg(satrec.mo),
    mean_motion: meanMotionRevPerDay,
    semimajor_axis_km: satrec.a * EARTH_RADIUS_KM,
    period_min: (2 * Math.PI) / satrec.no,
    apoapsis_km: satrec.alta * EARTH_RADIUS_KM,
    periapsis_km: satrec.altp * EARTH_RADIUS_KM,
    tle_line1: entry.TLE_LINE1,
    tle_line2: entry.TLE_LINE2,
  };
}
