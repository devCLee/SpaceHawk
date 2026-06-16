// Sensor-volume geometry for a satellite's nadir-pointing conical field of view.
// Pure functions (no Cesium) so the math is independently reasoned about and
// reused by both the globe overlay (CesiumComponent) and the info-panel readout.
// Display only — the Python engine remains authoritative for analysis
// (dev-plan §4.2).
//
// APPLIES TO ALL ORBIT REGIMES (LEO/MEO/GEO/HEO). The geometry is purely a
// function of altitude, so nothing here is LEO-specific. The only altitude-
// dependent subtlety — a high object (e.g. GEO) can see at most the *visible
// Earth cap* — is handled by clamping the half-angle to the Earth's angular
// radius (the horizon). With that clamp every regime yields a correct, bounded
// footprint; the sensor half-angle (not the orbit class) is what drives the
// footprint size.

/** WGS-84 mean Earth radius [km]. */
export const EARTH_RADIUS_KM = 6371;

/** Default sensor half-cone (nadir) angle [deg] when none is known per object. */
export const DEFAULT_SENSOR_HALF_ANGLE_DEG = 45;
/** UI slider bounds for the half-angle. */
export const MIN_SENSOR_HALF_ANGLE_DEG = 1;
export const MAX_SENSOR_HALF_ANGLE_DEG = 89;

const DEG = Math.PI / 180;

export interface SensorVolumeGeometry {
  /** The requested half-angle clamped to the horizon (Earth's angular radius). */
  effectiveHalfAngleDeg: number;
  /** True when the requested half-angle reached/exceeded the horizon and was
   *  clamped — the sensor sees the entire visible Earth cap (typical at GEO). */
  horizonLimited: boolean;
  /** Earth-central angle from the sub-satellite point to the footprint edge [deg]. */
  centralAngleDeg: number;
  /** Geodesic ground radius of the circular footprint [km] (= Rₑ · λ). The
   *  Cesium ground ellipse uses this directly (semiMajor/MinorAxis). */
  groundRadiusKm: number;
  /** Slant range from the satellite to the footprint edge [km]. */
  slantRangeKm: number;
  /** Fraction of Earth's surface inside the footprint [0..1]. */
  coverageFraction: number;
  /** Base radius of the rendered cone [km] (= Rₑ · sin λ — the rim's horizontal
   *  extent, so the cone rim sits over the footprint circle). */
  coneBaseRadiusKm: number;
  /** Length of the rendered cone [km], apex at the satellite down to a base disk
   *  whose rim coincides with the footprint circle on the curved surface. */
  coneLengthKm: number;
  /** Altitude of the cone's centre [km] (negative — the flat base disk sits
   *  below the surface so only the cone walls, i.e. the lines of sight to the
   *  footprint rim, show above ground). Apex = altitude, base = this − length/2. */
  coneCenterAltitudeKm: number;
}

/**
 * Sensor footprint geometry for a nadir-pointing conical sensor.
 *
 * `altitudeKm` is the satellite's height above the ellipsoid; `halfAngleDeg` is
 * the sensor's half-cone (nadir) angle. Returns `null` for a non-positive
 * altitude (object on/below the surface — e.g. unparseable propagation).
 *
 * Geometry (SMAD): with Earth angular radius ρ = asin(Rₑ/(Rₑ+h)), a ray at
 * nadir angle η ≤ ρ reaches the surface at elevation angle
 *   ε = acos(((Rₑ+h)/Rₑ) · sin η)
 * and Earth-central angle λ = 90° − η − ε. η is clamped to ρ (the horizon), so
 * a high object with a wide sensor simply yields its full visible-Earth cap.
 *
 * The rendered cone is placed so its rim lands exactly on the footprint circle
 * at every altitude: apex at the satellite (alt h, radius 0), base disk at
 * alt Rₑ(cos λ − 1) (below the surface) with radius Rₑ sin λ — the buried base
 * is hidden and the visible cone walls are the lines of sight to the rim.
 */
export function sensorVolumeGeometry(
  altitudeKm: number,
  halfAngleDeg: number
): SensorVolumeGeometry | null {
  if (!Number.isFinite(altitudeKm) || altitudeKm <= 0) return null;
  if (!Number.isFinite(halfAngleDeg) || halfAngleDeg <= 0) return null;

  const Re = EARTH_RADIUS_KM;
  const r = Re + altitudeKm;

  // Earth's angular radius from the satellite = the maximum nadir angle (the
  // line of sight grazing the horizon). Beyond it the sensor sees only space.
  const rho = Math.asin(Re / r);
  const etaReq = halfAngleDeg * DEG;
  const eta = Math.min(etaReq, rho);
  const horizonLimited = etaReq >= rho;

  // Elevation angle at the footprint edge (clamp the acos arg against FP drift).
  const cosEps = Math.min(1, Math.max(-1, (r / Re) * Math.sin(eta)));
  const eps = Math.acos(cosEps);
  const lambda = Math.max(0, Math.PI / 2 - eta - eps); // central angle [rad]

  const sinLambda = Math.sin(lambda);
  const groundRadiusKm = Re * lambda;
  const coneBaseRadiusKm = Re * sinLambda;
  const slantRangeKm =
    eta > 1e-9 ? (Re * sinLambda) / Math.sin(eta) : altitudeKm;
  const coverageFraction = (1 - Math.cos(lambda)) / 2;
  const sagKm = Re * (1 - Math.cos(lambda)); // how far the rim dips below tangent
  const coneLengthKm = altitudeKm + sagKm;
  const coneCenterAltitudeKm = (altitudeKm - sagKm) / 2;

  return {
    effectiveHalfAngleDeg: eta / DEG,
    horizonLimited,
    centralAngleDeg: lambda / DEG,
    groundRadiusKm,
    slantRangeKm,
    coverageFraction,
    coneBaseRadiusKm,
    coneLengthKm,
    coneCenterAltitudeKm,
  };
}
