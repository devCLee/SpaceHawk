// Observer-relative look angles + pass prediction (#9i). Computes azimuth /
// elevation / range of a satellite (from its TLE) as seen from a ground sensor,
// and predicts upcoming visible passes. Client-side display math (satellite.js,
// dev-plan §4.2); the engine remains authoritative for analysis.

import { twoline2satrec, propagate, gstime, eciToEcf, ecfToLookAngles } from "satellite.js";

const RAD2DEG = 180 / Math.PI;
const DEG2RAD = Math.PI / 180;

export interface Observer {
  latDeg: number;
  lonDeg: number;
  altKm: number;
}

export interface LookAngle {
  azimuthDeg: number;
  elevationDeg: number;
  rangeKm: number;
}

/** Look angle of a TLE from an observer at `date`, or null if SGP4 fails. */
export function lookAngleAt(
  line1: string,
  line2: string,
  observer: Observer,
  date: Date = new Date()
): LookAngle | null {
  const satrec = twoline2satrec(line1, line2);
  const pv = propagate(satrec, date);
  if (pv === null || pv.position == null) return null;
  const ecf = eciToEcf(pv.position, gstime(date));
  const la = ecfToLookAngles(
    {
      longitude: observer.lonDeg * DEG2RAD,
      latitude: observer.latDeg * DEG2RAD,
      height: observer.altKm,
    },
    ecf
  );
  return {
    azimuthDeg: la.azimuth * RAD2DEG,
    elevationDeg: la.elevation * RAD2DEG,
    rangeKm: la.rangeSat,
  };
}

export interface SatPass {
  riseTime: Date;
  setTime: Date;
  maxElevationDeg: number;
}

export interface PassOptions {
  start?: Date;
  durationHours?: number;
  stepSec?: number;
  minElevationDeg?: number;
}

/** Predict visible passes (elevation above the horizon gate) over a window. */
export function predictPasses(
  line1: string,
  line2: string,
  observer: Observer,
  opts: PassOptions = {}
): SatPass[] {
  const start = opts.start ?? new Date();
  const durationHours = opts.durationHours ?? 24;
  const stepSec = opts.stepSec ?? 30;
  const minElevationDeg = opts.minElevationDeg ?? 10;

  const satrec = twoline2satrec(line1, line2);
  const endMs = start.getTime() + durationHours * 3600 * 1000;
  const passes: SatPass[] = [];

  let inPass = false;
  let riseTime: Date | null = null;
  let maxEl = -90;

  for (let t = start.getTime(); t <= endMs; t += stepSec * 1000) {
    const date = new Date(t);
    const pv = propagate(satrec, date);
    if (pv === null || pv.position == null) continue;
    const ecf = eciToEcf(pv.position, gstime(date));
    const la = ecfToLookAngles(
      {
        longitude: observer.lonDeg * DEG2RAD,
        latitude: observer.latDeg * DEG2RAD,
        height: observer.altKm,
      },
      ecf
    );
    const elevationDeg = la.elevation * RAD2DEG;

    if (elevationDeg >= minElevationDeg) {
      if (!inPass) {
        inPass = true;
        riseTime = date;
        maxEl = elevationDeg;
      } else if (elevationDeg > maxEl) {
        maxEl = elevationDeg;
      }
    } else if (inPass && riseTime) {
      passes.push({ riseTime, setTime: date, maxElevationDeg: maxEl });
      inPass = false;
      riseTime = null;
      maxEl = -90;
    }
  }
  // Close an open pass at the window edge.
  if (inPass && riseTime) {
    passes.push({
      riseTime,
      setTime: new Date(endMs),
      maxElevationDeg: maxEl,
    });
  }
  return passes;
}
