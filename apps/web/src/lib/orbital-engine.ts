// Server-side client for the Orbital Engine (the Python domain/compute tier).
//
// The web/BFF tier is the only thing that talks to the engine, over a private
// network address (`ORBITAL_ENGINE_URL`). Keeping these calls server-side keeps
// source credentials and internal queries off the browser (dev-plan §4.1).
//
// Types are kept local for the thin slice; Stage 2 swaps in the generated client
// from `@spacehawk/shared-types` once the contract stabilises.

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
  const res = await fetch(`${ENGINE_URL}/catalog`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`orbital-engine /catalog failed: ${res.status}`);
  }
  return res.json() as Promise<CatalogObject[]>;
}
