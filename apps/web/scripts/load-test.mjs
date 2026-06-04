// Stage 3 render/propagation load test (dev-plan Stage 3 testing; roadmap KPI
// ≥10,000 objects). Benchmarks the per-tick SGP4 cost — the scalability
// bottleneck the Web Worker offloads — at 10k / 20k / 30k objects, and reports
// the binary state-payload budget. Exits non-zero if a per-tick propagation
// blows the budget, so it can gate CI.
//
//   node scripts/load-test.mjs

import {
  twoline2satrec,
  propagate,
  gstime,
  eciToGeodetic,
} from "satellite.js";

// A representative LEO TLE (ISS). Replicated to synthesise catalog scale; the
// per-object propagation cost is what we're measuring.
const L1 =
  "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9005";
const L2 =
  "2 25544  51.6400 208.0000 0006703 130.0000 325.0000 15.50000000    05";

const SIZES = [10000, 20000, 30000];
// Per-tick propagation budget: 100 ms per 10k objects. At a 1 Hz update cadence
// this leaves the worker thread >=90% idle headroom.
const BUDGET_MS_PER_10K = 100;
const F32_BYTES_PER_OBJ = 3 * 4; // lon/lat/alt as Float32
const F64_BYTES_PER_OBJ = 3 * 8; // lon/lat/alt as Float64

function fmtKB(bytes) {
  return `${(bytes / 1024).toFixed(0)} KB`;
}

let failed = false;
console.log("Stage 3 load test — SGP4 per-tick propagation\n");
console.log(
  "objects |  parse ms | propagate ms | ok    | f32 payload | f64 payload | budget"
);
console.log(
  "--------+-----------+--------------+-------+-------------+-------------+-------"
);

for (const n of SIZES) {
  const tParse0 = performance.now();
  const satrecs = new Array(n);
  for (let i = 0; i < n; i++) satrecs[i] = twoline2satrec(L1, L2);
  const parseMs = performance.now() - tParse0;

  const date = new Date();
  const gmst = gstime(date);
  const lon = new Float64Array(n);
  const lat = new Float64Array(n);
  const alt = new Float64Array(n);

  const tProp0 = performance.now();
  let ok = 0;
  for (let i = 0; i < n; i++) {
    const pv = propagate(satrecs[i], date);
    if (pv && pv.position) {
      const gd = eciToGeodetic(pv.position, gmst);
      lon[i] = gd.longitude;
      lat[i] = gd.latitude;
      alt[i] = gd.height;
      ok++;
    }
  }
  const propMs = performance.now() - tProp0;

  const budgetMs = BUDGET_MS_PER_10K * (n / 10000);
  const pass = propMs <= budgetMs;
  if (!pass) failed = true;

  console.log(
    `${String(n).padStart(7)} | ${parseMs.toFixed(0).padStart(9)} | ` +
      `${propMs.toFixed(0).padStart(12)} | ${String(ok).padStart(5)} | ` +
      `${fmtKB(n * F32_BYTES_PER_OBJ).padStart(11)} | ` +
      `${fmtKB(n * F64_BYTES_PER_OBJ).padStart(11)} | ` +
      `${pass ? "PASS" : "FAIL"} (<= ${budgetMs.toFixed(0)} ms)`
  );
}

console.log(
  `\nPayload budget: stream positions as Float32 (${F32_BYTES_PER_OBJ} B/object) ` +
    `→ ~${fmtKB(30000 * F32_BYTES_PER_OBJ)} for 30k objects per snapshot.`
);

if (failed) {
  console.error("\nLoad test FAILED: per-tick propagation exceeded budget.");
  process.exit(1);
}
console.log("\nLoad test passed.");
