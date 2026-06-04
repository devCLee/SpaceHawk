// Off-main-thread SGP4 propagation for catalog-scale rendering (dev-plan Stage 3
// "Web Worker for client-side display propagation", keeptrack pattern). The main
// thread sends the TLE set once (init) then a sim time per tick; the worker
// returns geodetic positions as transferable typed arrays in init order.

import {
  twoline2satrec,
  propagate,
  gstime,
  eciToGeodetic,
  degreesLat,
  degreesLong,
  type SatRec,
} from "satellite.js";

interface SatInput {
  line1: string;
  line2: string;
}

type InMessage =
  | { type: "init"; sats: SatInput[] }
  | { type: "propagate"; timeMs: number };

// `self` is the worker global; cast to the minimal surface we use so the file
// type-checks under the app's DOM lib without pulling in the webworker lib.
const ctx = self as unknown as {
  postMessage: (message: unknown, transfer?: Transferable[]) => void;
  addEventListener: (
    type: "message",
    listener: (e: MessageEvent<InMessage>) => void
  ) => void;
};

let satrecs: SatRec[] = [];

ctx.addEventListener("message", (e) => {
  const msg = e.data;
  if (msg.type === "init") {
    satrecs = msg.sats.map((s) => twoline2satrec(s.line1, s.line2));
    return;
  }
  if (msg.type === "propagate") {
    const date = new Date(msg.timeMs);
    const gmst = gstime(date);
    const n = satrecs.length;
    const lon = new Float64Array(n);
    const lat = new Float64Array(n);
    const alt = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      const pv = propagate(satrecs[i], date);
      if (pv === null || pv.position == null) {
        lon[i] = NaN;
        lat[i] = NaN;
        alt[i] = NaN;
        continue;
      }
      const gd = eciToGeodetic(pv.position, gmst);
      lon[i] = degreesLong(gd.longitude);
      lat[i] = degreesLat(gd.latitude);
      alt[i] = gd.height * 1000;
    }
    ctx.postMessage({ type: "positions", timeMs: msg.timeMs, lon, lat, alt }, [
      lon.buffer,
      lat.buffer,
      alt.buffer,
    ]);
  }
});
