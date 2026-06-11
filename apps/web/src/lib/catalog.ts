// Server-only: load the full globe catalog (live engine, else bundled snapshot).
//
// Relocated out of main/page.tsx so the catalog is fetched CLIENT-side via
// /api/catalog/all instead of being serialized into the RSC document on every
// request (the ~4MB / ~1MB-gz payload that dominated load). Imports the 4.15MB
// snapshot, so this file must only be pulled into server route handlers — never
// a client component (that would re-bundle the snapshot to the browser).

import mainData from "@/data/main.json";
import { fetchCatalog, type CatalogObject } from "@/lib/orbital-engine";
import type { TleObject } from "@/app/utils/sgp4FromTle";

// Minimum object count for the live engine catalog to be considered "real". An
// unseeded / freshly-migrated engine DB can return a degenerate handful (e.g. a
// single leftover ISS fixture row) — far fewer than a real ingest; below this
// floor we prefer the bundled snapshot so the globe always shows a full catalog.
export const MIN_LIVE_CATALOG = 50;

/** Map the engine's CatalogObject rows into the globe's TleObject shape. */
export function toTleEntries(rows: CatalogObject[]): TleObject[] {
  return rows
    .filter((r) => r.tle_line1 && r.tle_line2)
    .map((r) => ({
      TLE_LINE1: r.tle_line1 as string,
      TLE_LINE2: r.tle_line2 as string,
      OBJECT_NAME: r.object_name,
      OBJECT_ID: r.object_id,
      NORAD_CAT_ID: r.norad_cat_id,
      COUNTRY_CODE: r.country_code,
    }));
}

// Bundled catalog snapshot (~15k active objects; CelesTrak GP + SATCAT, built by
// scripts/build-snapshot.mjs) — the fallback when the engine is unavailable
// (e.g. local dev without the backend up). The file already matches the
// TleObject shape, so no remap is needed.
const fallbackEntries: TleObject[] = (mainData as TleObject[]).filter(
  (e) => e.TLE_LINE1 && e.TLE_LINE2
);

/**
 * The full globe catalog as TleObjects: the live engine catalog when healthy,
 * otherwise the bundled snapshot. Never throws — the globe always gets data.
 */
export async function loadGlobeCatalog(): Promise<TleObject[]> {
  try {
    const live = toTleEntries(await fetchCatalog());
    if (live.length < MIN_LIVE_CATALOG) {
      throw new Error(
        `engine catalog too small (${live.length}); using bundled snapshot`
      );
    }
    return live;
  } catch {
    return fallbackEntries;
  }
}
