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
