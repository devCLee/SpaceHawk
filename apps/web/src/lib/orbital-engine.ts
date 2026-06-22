// Server-side client for the Orbital Engine (the Python domain/compute tier).
//
// The web/BFF tier is the only thing that talks to the engine, over a private
// network address (`ORBITAL_ENGINE_URL`). Keeping these calls server-side keeps
// source credentials and internal queries off the browser (dev-plan §4.1).
//
// Types are kept local for the thin slice; Stage 2 swaps in the generated client
// from `@spacehawk/shared-types` once the contract stabilises.

import { engineAuthHeaders } from "@/lib/engineSession";

const ENGINE_URL = process.env.ORBITAL_ENGINE_URL ?? "http://localhost:8000";

export interface CatalogObject {
  object_id: string;
  norad_cat_id: number | null;
  object_name: string;
  object_type: string | null;
  country_code: string | null;
  tle_line0: string | null;
  tle_line1: string | null;
  tle_line2: string | null;
}

/** Fetch the current catalog from the engine. Throws on a non-2xx response. */
export async function fetchCatalog(): Promise<CatalogObject[]> {
  const res = await fetch(`${ENGINE_URL}/catalog`, {
    cache: "no-store",
    headers: await engineAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(`orbital-engine /catalog failed: ${res.status}`);
  }
  return res.json() as Promise<CatalogObject[]>;
}

export interface CatalogQuery {
  q?: string;
  object_type?: string;
  country_code?: string;
  limit?: number;
  offset?: number;
}

/** Query the catalog with filters (name/NORAD substring, type, country). */
export async function queryCatalog(
  query: CatalogQuery
): Promise<CatalogObject[]> {
  const params = new URLSearchParams();
  if (query.q) params.set("q", query.q);
  if (query.object_type) params.set("object_type", query.object_type);
  if (query.country_code) params.set("country_code", query.country_code);
  if (query.limit != null) params.set("limit", String(query.limit));
  if (query.offset != null) params.set("offset", String(query.offset));
  const res = await fetch(`${ENGINE_URL}/catalog?${params.toString()}`, {
    cache: "no-store",
    headers: await engineAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(`orbital-engine /catalog query failed: ${res.status}`);
  }
  return res.json() as Promise<CatalogObject[]>;
}

/** Full catalog record for the per-satellite info sidebar (#9h). Mirrors the
 * engine's `ObjectDetail` response model — the subset the sidebar renders. */
export interface ObjectDetail {
  object_id: string;
  norad_cat_id: number | null;
  intl_designator: string | null;
  object_name: string;
  object_type: string | null;
  country_code: string | null;
  launch_date: string | null;
  epoch: string | null;
  inclination: number | null;
  eccentricity: number | null;
  ra_of_asc_node: number | null;
  arg_of_pericenter: number | null;
  mean_anomaly: number | null;
  mean_motion: number | null;
  semimajor_axis_km: number | null;
  period_min: number | null;
  apoapsis_km: number | null;
  periapsis_km: number | null;
  tle_line1: string | null;
  tle_line2: string | null;
}

export type ConjunctionSeverity = "LOW" | "MOD" | "HIGH";

/** One screened conjunction (#9g). The Stage-4 screening service will populate
 * the engine `/conjunctions` endpoint; this is the contract the UI renders. */
export interface Conjunction {
  id: string;
  /** "CDM" (official message) or "SCREENING" (engine-computed). */
  source?: "CDM" | "SCREENING";
  cdm_id?: string | null;
  primary_object_id: string;
  primary_norad_cat_id?: number | null;
  primary_name: string;
  secondary_object_id: string;
  secondary_norad_cat_id?: number | null;
  secondary_name: string;
  /** Time of closest approach (ISO). */
  tca: string;
  miss_distance_km: number;
  relative_speed_km_s?: number | null;
  probability: number | null;
  severity: ConjunctionSeverity;
  screened_at?: string | null;
}

export interface ConjunctionsResult {
  /** False until the Stage-4 screening service is online. */
  available: boolean;
  conjunctions: Conjunction[];
}

/** Fetch screened conjunctions. Returns `available: false` until the engine's
 * Stage-4 `/conjunctions` endpoint exists (graceful, never throws). */
export async function fetchConjunctions(): Promise<ConjunctionsResult> {
  try {
    const res = await fetch(`${ENGINE_URL}/conjunctions`, {
      cache: "no-store",
      headers: await engineAuthHeaders(),
    });
    if (!res.ok) return { available: false, conjunctions: [] };
    const data = (await res.json()) as Conjunction[];
    return { available: true, conjunctions: data };
  } catch {
    return { available: false, conjunctions: [] };
  }
}

// --- Debris (CelesTrak fragmentation groups + collision risk) ---

/** One tracked-debris object with derived orbital params + risk. Mirrors the
 * engine `DebrisObject` response; the direct-CelesTrak / snapshot fallbacks
 * (lib/debris.ts) produce the same shape. */
export interface Debris {
  object_id: string;
  norad_cat_id: number | null;
  object_name: string;
  country_code: string | null;
  rcs_size: string | null;
  inclination: number | null;
  eccentricity: number | null;
  period_min: number | null;
  apoapsis_km: number | null;
  periapsis_km: number | null;
  mean_altitude_km: number | null;
  speed_km_s: number | null;
  /** 0-100 relative-risk index (density × velocity × size). */
  risk_score: number;
  /** Critical / High / Medium / Low. */
  risk_level: string;
  tle_line0: string | null;
  tle_line1: string | null;
  tle_line2: string | null;
}

export interface DebrisDensityBin {
  altitude_km: number;
  count: number;
}

/** Population-level debris risk analysis (engine `/debris/risk`). `conjunctions`
 * carry the real SGP4-screened probability-of-collision; empty until screening
 * has run with debris in the catalog. */
export interface DebrisRiskSummary {
  available: boolean;
  total: number;
  by_level: Record<string, number>;
  density_by_shell: DebrisDensityBin[];
  conjunctions: Conjunction[];
}

/** Fetch the engine's tracked-debris list. Returns null when the engine `/debris`
 * endpoint is unavailable so lib/debris.ts can fall back to a direct CelesTrak
 * pull or the bundled snapshot (never throws). */
export async function fetchDebris(): Promise<Debris[] | null> {
  try {
    const res = await fetch(`${ENGINE_URL}/debris?limit=20000`, {
      cache: "no-store",
      headers: await engineAuthHeaders(),
    });
    if (!res.ok) return null;
    return (await res.json()) as Debris[];
  } catch {
    return null;
  }
}

const EMPTY_DEBRIS_RISK: DebrisRiskSummary = {
  available: false,
  total: 0,
  by_level: {},
  density_by_shell: [],
  conjunctions: [],
};

/** Fetch the engine's debris risk analysis. Graceful: `available: false` (never
 * throws) when the engine endpoint is offline or screening hasn't populated. */
export async function fetchDebrisRisk(): Promise<DebrisRiskSummary> {
  try {
    const res = await fetch(`${ENGINE_URL}/debris/risk`, {
      cache: "no-store",
      headers: await engineAuthHeaders(),
    });
    if (!res.ok) return EMPTY_DEBRIS_RISK;
    const data = (await res.json()) as Omit<DebrisRiskSummary, "available">;
    return { available: true, ...data };
  } catch {
    return EMPTY_DEBRIS_RISK;
  }
}

export type AlertStatus = "NEW" | "ACK" | "DISMISSED";

/** One durable alert in the triage log (alert center). */
export interface Alert {
  id: string;
  type: string;
  severity: ConjunctionSeverity | null;
  object_id: string | null;
  conjunction_id: string | null;
  message: string;
  payload: Record<string, unknown>;
  status: AlertStatus;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  created_at: string | null;
}

/** Fetch the durable alert log, optionally filtered by triage status. */
export async function fetchAlerts(status?: string): Promise<Alert[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const res = await fetch(`${ENGINE_URL}/alerts?${params.toString()}`, {
    cache: "no-store",
    headers: await engineAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(`orbital-engine /alerts failed: ${res.status}`);
  }
  return res.json() as Promise<Alert[]>;
}

/** Acknowledge or dismiss an alert. Returns null on 404, throws on other errors. */
export async function acknowledgeAlert(
  id: string,
  body: { status: "ACK" | "DISMISSED"; acknowledged_by?: string }
): Promise<Alert | null> {
  const res = await fetch(
    `${ENGINE_URL}/alerts/${encodeURIComponent(id)}/ack`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(await engineAuthHeaders()) },
      body: JSON.stringify(body),
      cache: "no-store",
    }
  );
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`orbital-engine /alerts/${id}/ack failed: ${res.status}`);
  }
  return res.json() as Promise<Alert>;
}

/** Fetch one object's full detail. Returns null on 404, throws on other errors. */
export async function fetchObjectDetail(
  objectId: string
): Promise<ObjectDetail | null> {
  const res = await fetch(
    `${ENGINE_URL}/catalog/${encodeURIComponent(objectId)}`,
    { cache: "no-store", headers: await engineAuthHeaders() }
  );
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`orbital-engine /catalog/${objectId} failed: ${res.status}`);
  }
  return res.json() as Promise<ObjectDetail>;
}

export type ManeuverType =
  | "STATION_KEEPING"
  | "ORBIT_RAISE"
  | "ORBIT_LOWER"
  | "PHASING"
  | "RPO"
  | "UNKNOWN";

/** One detected maneuver (Stage 6 #10/#11). Mirrors the engine's
 * `ManeuverResponse`: the element deltas + Δv/RIC + rule-based purpose, plus the
 * V-pattern evidence (`detection_statistic`) that the explainability UI renders. */
export interface Maneuver {
  id: string;
  object_id: string;
  norad_cat_id: number | null;
  object_name: string;
  epoch_before: string;
  epoch_after: string;
  detected_epoch: string;
  delta_sma_km: number;
  delta_ecc: number;
  delta_inc_deg: number;
  delta_raan_deg: number;
  detection_statistic: number;
  confidence: number;
  sma_before_km: number | null;
  inclination_deg: number | null;
  delta_v_m_s: number | null;
  ric_radial_m_s: number | null;
  ric_in_track_m_s: number | null;
  ric_cross_track_m_s: number | null;
  maneuver_type: ManeuverType;
  detected_at: string | null;
}

/** One object's behavioral fingerprint (Stage 6 #14). Mirrors `BaselineResponse`. */
export interface ManeuverBaseline {
  object_id: string;
  object_name: string;
  sample_count: number;
  mean_interval_days: number | null;
  interval_mad_days: number | null;
  mean_delta_v_m_s: number;
  delta_v_mad_m_s: number;
  type_distribution: Record<string, number>;
  last_epoch: string;
  updated_at: string | null;
}

export interface ManeuversResult {
  /** False until the Stage-6 maneuver service is online (or access is denied). */
  available: boolean;
  maneuvers: Maneuver[];
}

export interface BaselinesResult {
  available: boolean;
  baselines: ManeuverBaseline[];
}

/** Fetch detected maneuvers, optionally for one object. Graceful: returns
 * `available: false` (never throws) when the engine endpoint is offline or the
 * caller lacks the MANEUVER_INTEL grant. */
export async function fetchManeuvers(
  objectId?: string
): Promise<ManeuversResult> {
  try {
    const params = new URLSearchParams();
    if (objectId) params.set("object_id", objectId);
    const res = await fetch(`${ENGINE_URL}/maneuvers?${params.toString()}`, {
      cache: "no-store",
      headers: await engineAuthHeaders(),
    });
    if (!res.ok) return { available: false, maneuvers: [] };
    return { available: true, maneuvers: (await res.json()) as Maneuver[] };
  } catch {
    return { available: false, maneuvers: [] };
  }
}

/** Fetch the per-object behavioral baselines. Graceful (see `fetchManeuvers`). */
export async function fetchBaselines(): Promise<BaselinesResult> {
  try {
    const res = await fetch(`${ENGINE_URL}/maneuvers/baselines`, {
      cache: "no-store",
      headers: await engineAuthHeaders(),
    });
    if (!res.ok) return { available: false, baselines: [] };
    return { available: true, baselines: (await res.json()) as ManeuverBaseline[] };
  } catch {
    return { available: false, baselines: [] };
  }
}
