import {
  twoline2satrec,
  propagate,
  gstime,
  eciToGeodetic,
  degreesLat,
  degreesLong,
} from "satellite.js";

export interface TleObject {
  TLE_LINE1: string;
  TLE_LINE2: string;
  OBJECT_NAME?: string;
  /** Canonical catalog id (USOID) — stable handle for click-selection. */
  OBJECT_ID?: string;
  NORAD_CAT_ID?: number | null;
}

/**
 * Runs one SGP4 propagation for the given TLE at the given time.
 * Logs position (ECI km) and velocity (km/s) to the console and returns the result.
 */
export function runOneSgp4Calculation(
  line1: string,
  line2: string,
  date: Date = new Date()
): {
  position: { x: number; y: number; z: number };
  velocity: { x: number; y: number; z: number };
} | null {
  const satrec = twoline2satrec(line1, line2);
  const positionAndVelocity = propagate(satrec, date);

  if (positionAndVelocity === null) {
    console.error(
      "SGP4 propagation failed:",
      (satrec as { error?: number }).error
    );
    return null;
  }

  const { position, velocity } = positionAndVelocity;
  const result = {
    position: { x: position.x, y: position.y, z: position.z },
    velocity: { x: velocity.x, y: velocity.y, z: velocity.z },
  };
  console.log("SGP4 result (ECI km, km/s):", result);
  return result;
}

/**
 * Runs one SGP4 propagation and converts the result into geodetic
 * latitude/longitude/height (WGS‑84) suitable for visualization.
 */
export function runOneSgp4ToLatLonAlt(
  line1: string,
  line2: string,
  date: Date = new Date()
): { lat: number; lng: number; height: number } | null {
  const satrec = twoline2satrec(line1, line2);
  const positionAndVelocity = propagate(satrec, date);

  if (positionAndVelocity === null || positionAndVelocity.position == null) {
    console.error(
      "SGP4 propagation (geodetic) failed:",
      (satrec as { error?: number }).error
    );
    return null;
  }

  const gmst = gstime(date);
  const positionGd = eciToGeodetic(positionAndVelocity.position, gmst);

  const lat = degreesLat(positionGd.latitude);
  const lng = degreesLong(positionGd.longitude);
  const height = positionGd.height;

  return { lat, lng, height };
}

export type OrbitRegime = "LEO" | "MEO" | "GEO" | "HEO";

export interface OrbitParams {
  inclinationDeg: number;
  periodMin: number;
  eccentricity: number;
  regime: OrbitRegime;
}

/** Classify an orbit regime from period + eccentricity (coarse, for find-sat). */
function classifyRegime(periodMin: number, eccentricity: number): OrbitRegime {
  if (eccentricity > 0.25) return "HEO";
  if (periodMin < 128) return "LEO";
  if (periodMin >= 1410 && periodMin <= 1450) return "GEO";
  return "MEO";
}

/** Derive inclination / period / eccentricity / regime from a TLE (#9b). */
export function deriveOrbitParams(
  line1: string,
  line2: string
): OrbitParams | null {
  const satrec = twoline2satrec(line1, line2);
  if (!satrec.no || satrec.no <= 0) return null;
  const periodMin = (2 * Math.PI) / satrec.no; // satrec.no is rad/min
  const inclinationDeg = (satrec.inclo * 180) / Math.PI;
  const eccentricity = satrec.ecco;
  return {
    inclinationDeg,
    periodMin,
    eccentricity,
    regime: classifyRegime(periodMin, eccentricity),
  };
}

export interface Sgp4State {
  /** Geodetic position (WGS-84). */
  lat: number;
  lng: number;
  /** Altitude in km. */
  altKm: number;
  /** ECI velocity components (km/s). */
  velocity: { x: number; y: number; z: number };
  /** Speed magnitude (km/s). */
  speedKmS: number;
}

/**
 * Propagate a TLE to geodetic position + ECI velocity at `date`, for the info
 * sidebar's live Current-Position / Orbital-Velocity readout. Display only —
 * the Python engine remains authoritative for analysis (dev-plan §4.2). Unlike
 * {@link runOneSgp4Calculation} this does not log to the console (it runs on a
 * timer).
 */
export function runSgp4State(
  line1: string,
  line2: string,
  date: Date = new Date()
): Sgp4State | null {
  const satrec = twoline2satrec(line1, line2);
  const pv = propagate(satrec, date);
  if (pv === null || pv.position == null || pv.velocity == null) {
    return null;
  }

  const gd = eciToGeodetic(pv.position, gstime(date));
  const { x, y, z } = pv.velocity;
  return {
    lat: degreesLat(gd.latitude),
    lng: degreesLong(gd.longitude),
    altKm: gd.height,
    velocity: { x, y, z },
    speedKmS: Math.sqrt(x * x + y * y + z * z),
  };
}

