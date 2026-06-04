// Placeholder ground-sensor catalog (#9c). Approximate coordinates for ROK /
// allied sites; `rangeKm` is a nominal coverage radius for display only.
// Replace with an accredited sensor-site dataset before operational use
// (dev-plan Stage 3 Dependencies).

export interface Sensor {
  id: string;
  name: string;
  country: string;
  latDeg: number;
  lonDeg: number;
  altKm: number;
  /** Nominal coverage radius (km) for the globe ring + pass min-range gate. */
  rangeKm: number;
}

export const SENSORS: Sensor[] = [
  { id: "kari-daejeon", name: "KARI Daejeon", country: "ROK", latDeg: 36.38, lonDeg: 127.36, altKm: 0.07, rangeKm: 2200 },
  { id: "jeju", name: "Jeju Tracking", country: "ROK", latDeg: 33.45, lonDeg: 126.56, altKm: 0.1, rangeKm: 2200 },
  { id: "osan", name: "Osan AB", country: "ROK", latDeg: 37.09, lonDeg: 127.03, altKm: 0.02, rangeKm: 2000 },
  { id: "kaena", name: "Kaena Point (HI)", country: "US", latDeg: 21.57, lonDeg: -158.27, altKm: 0.3, rangeKm: 2600 },
  { id: "diego-garcia", name: "Diego Garcia", country: "US", latDeg: -7.41, lonDeg: 72.45, altKm: 0.0, rangeKm: 2600 },
  { id: "vandenberg", name: "Vandenberg SFB", country: "US", latDeg: 34.74, lonDeg: -120.57, altKm: 0.1, rangeKm: 2600 },
];

export function sensorById(id: string | null): Sensor | null {
  if (!id) return null;
  return SENSORS.find((s) => s.id === id) ?? null;
}
