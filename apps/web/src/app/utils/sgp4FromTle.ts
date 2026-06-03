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

