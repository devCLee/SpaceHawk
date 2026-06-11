// A single static TLE for the client-side SGP4 self-check (Sgp4ConsoleLog).
//
// Previously page.tsx imported the whole ~4.15MB catalog snapshot just to read
// row [0] for this diagnostic, dragging the full catalog into the "/" route's
// server chunk. The check only needs ONE valid TLE to prove the propagation
// pipeline runs, so a fixed sample is enough (the canonical ISS example from the
// satellite.js docs; its old epoch is irrelevant to a pipeline self-test).

export const SAMPLE_TLE = {
  name: "ISS (ZARYA)",
  line1: "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927",
  line2: "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537",
};
