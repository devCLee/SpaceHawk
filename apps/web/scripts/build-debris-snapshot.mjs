// Build the bundled debris snapshot (src/data/debris.json) — the offline/CI
// fallback for the debris layer when neither the orbital-engine nor CelesTrak is
// reachable. Mirrors scripts/build-snapshot.mjs (the active-catalog snapshot).
//
//   node scripts/build-debris-snapshot.mjs
//
// Pulls the three major fragmentation-cloud groups from CelesTrak (TLE export)
// and writes compact {OBJECT_NAME, NORAD_CAT_ID, TLE_LINE0/1/2} records. Risk is
// derived at load time (lib/debris.ts), so it is intentionally NOT stored here.

import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const GP_URL = "https://celestrak.org/NORAD/elements/gp.php";
const GROUPS = ["fengyun-1c-debris", "cosmos-2251-debris", "iridium-33-debris"];

const here = dirname(fileURLToPath(import.meta.url));
const outPath = resolve(here, "../src/data/debris.json");

function parseTle(text) {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trimEnd())
    .filter((l) => l.length > 0);
  const out = [];
  for (let i = 0; i + 2 < lines.length; i += 3) {
    const [l0, l1, l2] = [lines[i], lines[i + 1], lines[i + 2]];
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

const records = [];
for (const group of GROUPS) {
  const res = await fetch(`${GP_URL}?GROUP=${group}&FORMAT=tle`);
  if (!res.ok) {
    console.error(`skip ${group}: HTTP ${res.status}`);
    continue;
  }
  const recs = parseTle(await res.text());
  console.log(`${group}: ${recs.length}`);
  records.push(...recs);
}

writeFileSync(outPath, JSON.stringify(records));
console.log(`wrote ${records.length} debris records -> ${outPath}`);
