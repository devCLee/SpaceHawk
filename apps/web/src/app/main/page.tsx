import DashboardShell from "../Components/DashboardShell";
import AlertToast from "../Components/AlertToast";
import mainData from "@/data/main.json";
import type { TleObject } from "../utils/sgp4FromTle";
import { fetchCatalog, type CatalogObject } from "@/lib/orbital-engine";

// Fetch the live catalog on every request (no static caching of orbital state).
export const dynamic = "force-dynamic";

function toTleEntries(rows: CatalogObject[]): TleObject[] {
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
// (e.g. local dev without the backend up). The live source is the engine. The
// file already matches the TleObject shape, so no remap is needed.
const fallbackEntries = (mainData as TleObject[]).filter(
  (e) => e.TLE_LINE1 && e.TLE_LINE2
);

// Minimum object count for the live engine catalog to be considered "real".
// An unseeded / freshly-migrated engine DB can return a degenerate handful (e.g.
// a single leftover ISS fixture row from a test run) — far fewer than a real
// ingest and not worth rendering over the bundled snapshot. Below this floor we
// prefer the snapshot so the globe always shows a full catalog (same intent as
// the "engine unavailable" fallback). A successful ingest returns the full
// Celestrak "active" set (~15k objects, per ingest_limit).
const MIN_LIVE_CATALOG = 50;

export default async function MainPage() {
  let tleEntries: TleObject[];
  try {
    const live = toTleEntries(await fetchCatalog());
    if (live.length < MIN_LIVE_CATALOG) {
      throw new Error(
        `engine catalog too small (${live.length}); using bundled snapshot`
      );
    }
    tleEntries = live;
  } catch {
    tleEntries = fallbackEntries;
  }

  return (
    <>
      <DashboardShell tleEntries={tleEntries} />
      <AlertToast />
    </>
  );
}
