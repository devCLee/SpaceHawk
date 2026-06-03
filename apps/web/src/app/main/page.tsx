import CesiumWrapper from "../Components/CesiumWrapper";
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
    }));
}

// Bundled Space-Track snapshot — the fallback when the engine is unavailable
// (e.g. local dev without the backend up). The slice's live source is the engine.
const fallbackEntries = (
  mainData as Array<{ TLE_LINE1?: string; TLE_LINE2?: string; OBJECT_NAME?: string }>
).filter((e) => e.TLE_LINE1 && e.TLE_LINE2) as TleObject[];

export default async function MainPage() {
  let tleEntries: TleObject[];
  try {
    tleEntries = toTleEntries(await fetchCatalog());
    if (tleEntries.length === 0) {
      throw new Error("engine returned an empty catalog");
    }
  } catch {
    tleEntries = fallbackEntries;
  }

  return <CesiumWrapper positions={[]} tleEntries={tleEntries} />;
}
