// Regression check for the snapshot-backed object detail fallback
// (src/lib/snapshotCatalog.ts). The globe renders the bundled snapshot when the
// engine catalog is unavailable/sparse; this guards that clicking such an object
// can still produce a populated detail (the bug: /api/catalog/{id} 404'd because
// it only read the engine DB).
//
// The .ts module can't be imported from plain Node (path aliases + JSON import),
// so this mirrors its derivation against the REAL main.json + satellite.js and
// asserts the values match the source TLE. If this drifts from
// snapshotCatalog.ts, fix both.
//
// Usage: node scripts/verify-snapshot-detail.mjs

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { twoline2satrec } from "satellite.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const snapshot = JSON.parse(
  fs.readFileSync(path.join(__dirname, "../src/data/main.json"), "utf8")
);

const EARTH_RADIUS_KM = 6378.135;
const toDeg = (rad) => (rad * 180) / Math.PI;

const index = new Map();
for (const e of snapshot) {
  if (e.OBJECT_ID && e.TLE_LINE1 && e.TLE_LINE2) index.set(e.OBJECT_ID, e);
}

function findSnapshotDetail(objectId) {
  const entry = index.get(objectId);
  if (!entry?.TLE_LINE1 || !entry.TLE_LINE2) return null;
  const s = twoline2satrec(entry.TLE_LINE1, entry.TLE_LINE2);
  if (!s.no || s.no <= 0) return null;
  return {
    object_id: entry.OBJECT_ID ?? objectId,
    norad_cat_id: entry.NORAD_CAT_ID ?? null,
    intl_designator: entry.OBJECT_ID ?? null,
    object_name: entry.OBJECT_NAME ?? entry.OBJECT_ID ?? objectId,
    object_type: null,
    country_code: entry.COUNTRY_CODE ?? null,
    launch_date: null,
    epoch: Number.isFinite(s.jdsatepoch)
      ? new Date((s.jdsatepoch - 2440587.5) * 86400000).toISOString()
      : null,
    inclination: toDeg(s.inclo),
    eccentricity: s.ecco,
    ra_of_asc_node: toDeg(s.nodeo),
    arg_of_pericenter: toDeg(s.argpo),
    mean_anomaly: toDeg(s.mo),
    mean_motion: (s.no * 1440) / (2 * Math.PI),
    semimajor_axis_km: s.a * EARTH_RADIUS_KM,
    period_min: (2 * Math.PI) / s.no,
    apoapsis_km: s.alta * EARTH_RADIUS_KM,
    periapsis_km: s.altp * EARTH_RADIUS_KM,
    tle_line1: entry.TLE_LINE1,
    tle_line2: entry.TLE_LINE2,
  };
}

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}`);
  if (!ok) failures++;
};
const near = (a, b, tol) => Math.abs(a - b) <= tol;

// The object from the reported bug (GSAT0221 / GALILEO 25). Expected values come
// straight from its TLE in the snapshot.
const ID = "2018-060A";
const d = findSnapshotDetail(ID);

check(`snapshot contains ${ID}`, d !== null);
if (d) {
  check("object_id", d.object_id === ID);
  check("intl_designator", d.intl_designator === ID);
  check("norad_cat_id 43564", d.norad_cat_id === 43564);
  check("object_name present", d.object_name === "GSAT0221 (GALILEO 25)");
  check("country_code ESA", d.country_code === "ESA");
  check("inclination ~57.1747", near(d.inclination, 57.1747, 1e-3));
  check("eccentricity ~0.0002733", near(d.eccentricity, 0.0002733, 1e-6));
  check("ra_of_asc_node ~342.0686", near(d.ra_of_asc_node, 342.0686, 1e-3));
  check("arg_of_pericenter ~309.4515", near(d.arg_of_pericenter, 309.4515, 1e-3));
  check("mean_anomaly ~50.5379", near(d.mean_anomaly, 50.5379, 1e-3));
  check("mean_motion ~1.70476", near(d.mean_motion, 1.70476038, 1e-4));
  check("semimajor_axis ~29600 km (MEO)", near(d.semimajor_axis_km, 29600, 50));
  check("period ~844 min", near(d.period_min, 844.69, 1));
  check("apoapsis > periapsis", d.apoapsis_km > d.periapsis_km);
  check("epoch is 2026-06-06", d.epoch?.startsWith("2026-06-06") === true);
  check("tle lines carried through", !!d.tle_line1 && !!d.tle_line2);
  check("object_type null (not in snapshot)", d.object_type === null);
}

// A NORAD id is NOT an OBJECT_ID key — must miss (and the engine stays
// authoritative), and a bogus id returns null rather than throwing.
check("unknown id -> null", findSnapshotDetail("NOPE-9999Z") === null);
check("numeric NORAD not an OBJECT_ID key", findSnapshotDetail("43564") === null);

console.log(failures === 0 ? "\nAll checks passed." : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
