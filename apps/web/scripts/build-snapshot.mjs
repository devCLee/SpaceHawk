// Regenerate the bundled catalog snapshot (apps/web/src/data/main.json) from a
// large CelesTrak "active" GP set, so the offline/dev fallback shows a full
// catalog (~15k satellites) instead of the original 268-object demo slice.
//
// CelesTrak's GP JSON carries the OMM mean elements but NOT the raw TLE lines,
// and its TLE export is rate-limited per group. So we reconstruct the TLE lines
// deterministically from the OMM fields (the inverse of satellite.js's
// twoline2satrec) and validate the encoder byte-for-byte against records that
// already ship with real TLE lines. COUNTRY_CODE (absent from the GP feed) is
// enriched from CelesTrak's SATCAT (OWNER), so the offline globe's
// colour-by-nation filter keeps working. Output records match the frontend's
// TleObject shape exactly (TLE_LINE1/2, OBJECT_NAME, OBJECT_ID, NORAD_CAT_ID,
// COUNTRY_CODE) — nothing the UI doesn't read.
//
// Usage:
//   node scripts/build-snapshot.mjs validate            # prove the encoder vs ground truth
//   node scripts/build-snapshot.mjs build <omm.json> <satcat.csv> <out.json>

import fs from "node:fs";
import { twoline2satrec, propagate } from "satellite.js";

// --- TLE field encoders (inverse of the TLE column spec) ---

function checksum(line68) {
  let sum = 0;
  for (const ch of line68.slice(0, 68)) {
    if (ch >= "0" && ch <= "9") sum += Number(ch);
    else if (ch === "-") sum += 1;
  }
  return String(sum % 10);
}

/** NORAD id in 5 cols. The bundled snapshot space-pads (matching the existing
 * data + CelesTrak's looser form); padding is cosmetic — satellite.js parses
 * either. All active objects are < 100000, so no Alpha-5 encoding is needed. */
function norad5(id) {
  return String(Math.trunc(Number(id))).padStart(5, " ").slice(-5);
}

/** International designator: "1998-067A" -> "98067A  " (cols 10-17). */
function intlField(objectId) {
  if (!objectId) return " ".repeat(8);
  const compact = String(objectId).replace(/-/g, "");
  const yyTail = compact.length >= 2 ? compact.slice(2) : compact; // drop century
  return yyTail.padEnd(8, " ").slice(0, 8);
}

/** ISO epoch (UTC) -> "YYDDD.DDDDDDDD" (cols 19-32). */
function epochField(iso) {
  const m = String(iso).match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?/
  );
  if (!m) throw new Error(`bad epoch: ${iso}`);
  const [, Y, Mo, D, h, mi, s, frac] = m;
  const year = Number(Y);
  const startOfYear = Date.UTC(year, 0, 1);
  const fracMs = frac ? Number(`0.${frac}`) * 1000 : 0;
  const epochMs =
    Date.UTC(year, Number(Mo) - 1, Number(D), Number(h), Number(mi), Number(s)) +
    fracMs;
  const dayOfYear = (epochMs - startOfYear) / 86400000 + 1; // 1-based, fractional
  const [intPart, decPart] = dayOfYear.toFixed(8).split(".");
  const yy = String(year % 100).padStart(2, "0");
  return yy + intPart.padStart(3, "0") + "." + decPart;
}

/** First time derivative of mean motion -> " .NNNNNNNN" (cols 34-43). */
function mmDotField(v) {
  const sign = v < 0 ? "-" : " ";
  return sign + Math.abs(v).toFixed(8).replace(/^0/, "");
}

/** Assumed-decimal exponential (cols 45-52 ddot, 54-61 bstar): "±NNNNN±E". */
function expField(v) {
  if (!v || Math.abs(v) < 1e-30) return " 00000-0";
  const sign = v < 0 ? "-" : " ";
  let a = Math.abs(v);
  let exp = 0;
  while (a >= 1) { a /= 10; exp += 1; }
  while (a < 0.1) { a *= 10; exp -= 1; }
  let mant = Math.round(a * 1e5);
  if (mant === 100000) { mant = 10000; exp += 1; }
  const expSign = exp < 0 ? "-" : "+";
  return sign + String(mant).padStart(5, "0") + expSign + String(Math.abs(exp));
}

/** Fixed 8-col, 4-decimal angle (incl/raan/argp/ma). */
function angle84(v) {
  return Number(v).toFixed(4).padStart(8, " ");
}

/** Eccentricity -> 7 assumed-decimal digits (cols 27-33). */
function eccField(v) {
  return String(Math.round(Number(v) * 1e7)).padStart(7, "0").slice(-7);
}

/** Mean motion -> 11 cols, 8 decimals (cols 53-63). */
function mmField(v) {
  return Number(v).toFixed(8).padStart(11, " ");
}

function int4(v) {
  return String(Math.trunc(Number(v) || 0) % 10000).padStart(4, " ");
}
function int5(v) {
  return String(Math.trunc(Number(v) || 0) % 100000).padStart(5, " ");
}

/** Build TLE_LINE1 / TLE_LINE2 from an OMM record. */
function ommToTle(o) {
  const id = norad5(o.NORAD_CAT_ID);
  const cls = o.CLASSIFICATION_TYPE || "U";
  const eph = String(o.EPHEMERIS_TYPE ?? 0).trim() || "0";

  const l1body =
    "1 " + id + cls + " " + intlField(o.OBJECT_ID) + " " +
    epochField(o.EPOCH) + " " + mmDotField(Number(o.MEAN_MOTION_DOT)) + " " +
    expField(Number(o.MEAN_MOTION_DDOT)) + " " + expField(Number(o.BSTAR)) +
    " " + eph + " " + int4(o.ELEMENT_SET_NO);

  const l2body =
    "2 " + id + " " + angle84(o.INCLINATION) + " " + angle84(o.RA_OF_ASC_NODE) +
    " " + eccField(o.ECCENTRICITY) + " " + angle84(o.ARG_OF_PERICENTER) + " " +
    angle84(o.MEAN_ANOMALY) + " " + mmField(o.MEAN_MOTION) + int5(o.REV_AT_EPOCH);

  if (l1body.length !== 68) throw new Error(`L1 len ${l1body.length}: ${l1body}`);
  if (l2body.length !== 68) throw new Error(`L2 len ${l2body.length}: ${l2body}`);
  return [l1body + checksum(l1body), l2body + checksum(l2body)];
}

// --- validate: encode the shipped records, compare to their real TLE lines ---

function validate(groundTruthPath) {
  if (!groundTruthPath) {
    console.error(
      "validate needs a path to an OMM-bearing snapshot WITH real TLE lines\n" +
        "(the original Space-Track main.json), e.g.:\n" +
        "  node scripts/build-snapshot.mjs validate /tmp/main.orig.json"
    );
    process.exit(2);
  }
  const data = JSON.parse(fs.readFileSync(groundTruthPath, "utf8"));
  let exact = 0, parseOk = 0, total = 0, mismatch = [];
  for (const o of data) {
    if (!o.TLE_LINE1 || !o.TLE_LINE2) continue;
    total += 1;
    let l1, l2;
    try {
      [l1, l2] = ommToTle(o);
    } catch (e) {
      mismatch.push({ name: o.OBJECT_NAME, err: String(e) });
      continue;
    }
    const byteExact = l1 === o.TLE_LINE1 && l2 === o.TLE_LINE2;
    if (byteExact) exact += 1;

    // Position-equivalence check: reconstructed vs real must propagate alike.
    const a = propagate(twoline2satrec(l1, l2), new Date());
    const b = propagate(twoline2satrec(o.TLE_LINE1, o.TLE_LINE2), new Date());
    if (a?.position && b?.position) {
      const d = Math.hypot(
        a.position.x - b.position.x,
        a.position.y - b.position.y,
        a.position.z - b.position.z
      );
      if (d < 0.001) parseOk += 1; // < 1 m
      else if (!byteExact) mismatch.push({ name: o.OBJECT_NAME, deltaKm: d, l1, real1: o.TLE_LINE1, l2, real2: o.TLE_LINE2 });
    }
  }
  console.log(`ground-truth records: ${total}`);
  console.log(`byte-exact L1+L2:     ${exact} (${((exact / total) * 100).toFixed(1)}%)`);
  console.log(`position-equivalent:  ${parseOk} (${((parseOk / total) * 100).toFixed(1)}%)`);
  if (mismatch.length) {
    console.log(`\nFIRST MISMATCHES (${mismatch.length}):`);
    for (const m of mismatch.slice(0, 5)) console.log(JSON.stringify(m, null, 2));
  }
}

// --- build: OMM JSON + SATCAT -> slim main.json ---

function parseSatcat(csvPath) {
  const text = fs.readFileSync(csvPath, "utf8");
  const lines = text.split(/\r?\n/);
  const header = lines[0].split(",");
  const iNorad = header.indexOf("NORAD_CAT_ID");
  const iOwner = header.indexOf("OWNER");
  const iType = header.indexOf("OBJECT_TYPE");
  const byNorad = new Map();
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i]) continue;
    const c = lines[i].split(",");
    const norad = Number(c[iNorad]);
    if (!norad) continue;
    byNorad.set(norad, { owner: c[iOwner] || null, type: c[iType] || null });
  }
  return byNorad;
}

function build(ommPath, satcatPath, outPath) {
  const omm = JSON.parse(fs.readFileSync(ommPath, "utf8"));
  const satcat = parseSatcat(satcatPath);
  const out = [];
  let skipped = 0;
  for (const o of omm) {
    let l1, l2;
    try {
      [l1, l2] = ommToTle(o);
    } catch {
      skipped += 1;
      continue;
    }
    // Guard: every emitted record must parse + propagate.
    const pv = propagate(twoline2satrec(l1, l2), new Date());
    if (!pv?.position) { skipped += 1; continue; }

    // Emit exactly the TleObject shape the frontend consumes (sgp4FromTle.ts) —
    // no TLE_LINE0/OBJECT_TYPE (read by no consumer; "active" is ~all PAYLOAD),
    // so the `as TleObject[]` cast in main/page.tsx is accurate and the payload
    // stays as small as possible for the bundled fallback.
    const meta = satcat.get(Number(o.NORAD_CAT_ID)) || {};
    out.push({
      TLE_LINE1: l1,
      TLE_LINE2: l2,
      OBJECT_NAME: o.OBJECT_NAME,
      OBJECT_ID: o.OBJECT_ID,
      NORAD_CAT_ID: Number(o.NORAD_CAT_ID),
      COUNTRY_CODE: meta.owner,
    });
  }
  fs.writeFileSync(outPath, JSON.stringify(out));
  const bytes = fs.statSync(outPath).size;
  console.log(`wrote ${out.length} objects (skipped ${skipped}) -> ${outPath}`);
  console.log(`file size: ${(bytes / 1024 / 1024).toFixed(2)} MB`);
  const withCountry = out.filter((o) => o.COUNTRY_CODE).length;
  console.log(`with COUNTRY_CODE: ${withCountry} (${((withCountry / out.length) * 100).toFixed(1)}%)`);
}

const [cmd, ...rest] = process.argv.slice(2);
if (cmd === "validate") validate(rest[0]);
else if (cmd === "build") build(rest[0], rest[1], rest[2]);
else
  console.log(
    "usage:\n" +
      "  build-snapshot.mjs build <omm.json> <satcat.csv> <out.json>\n" +
      "  build-snapshot.mjs validate <ground-truth-omm+tle.json>"
  );
