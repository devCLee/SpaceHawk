"use client";

// Catalog-view state shared between the control panels and the globe:
//   - country filter (#9d) and constellation filter (#9e) — the globe colours
//     matches and dims the rest;
//   - watchlist (#9f) — user-managed object-of-interest ids, persisted to
//     localStorage; the globe marks them and the watchlist panel lists them.
//     (Distinct from the RPO protected-asset list in Stage 6, but a future
//     backend list model can back both — dev-plan Stage 3.)
//   - visualization options (#viz) — the colour-by mode (object class / orbit
//     regime) and the set of categories hidden from the globe, persisted so the
//     analyst's chosen view survives a reload.

import React from "react";
import type { ColorMode } from "../data/visualization";

const WATCHLIST_KEY = "spacehawk.watchlist";
const VIZ_KEY = "spacehawk.viz";

interface CatalogViewContextValue {
  countryFilter: string | null;
  setCountryFilter: (code: string | null) => void;
  constellationFilter: string | null;
  setConstellationFilter: (key: string | null) => void;
  watchlist: string[];
  isWatched: (id: string) => boolean;
  toggleWatch: (id: string) => void;
  /** Globe colour-by axis: object class or orbit regime. */
  colorMode: ColorMode;
  setColorMode: (mode: ColorMode) => void;
  /** Category keys hidden from the globe (under the active colour mode). */
  hiddenCategories: string[];
  isCategoryHidden: (key: string) => boolean;
  toggleCategory: (key: string) => void;
}

const CatalogViewContext =
  React.createContext<CatalogViewContextValue | null>(null);

export function CatalogViewProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [countryFilter, setCountryFilter] = React.useState<string | null>(null);
  const [constellationFilter, setConstellationFilter] = React.useState<
    string | null
  >(null);
  const [watchlist, setWatchlist] = React.useState<string[]>([]);
  // Default to orbit-regime colouring: it is derived from each TLE, so it shows
  // full LEO/MEO/GEO/HEO variety on both the live engine catalogue AND the
  // active-only bundled snapshot (object_type colouring needs the live engine).
  const [colorMode, setColorMode] = React.useState<ColorMode>("regime");
  const [hiddenCategories, setHiddenCategories] = React.useState<string[]>([]);

  // Load the persisted watchlist + viz options once on mount. This is
  // intentionally a post-mount setState (not a lazy initializer): reading
  // localStorage during render would diverge between the server ([]) and the
  // client, reintroducing a hydration mismatch. Safe here — it runs once and is
  // not a render loop.
  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(WATCHLIST_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- hydration-safe one-time load from localStorage
      if (raw) setWatchlist(JSON.parse(raw) as string[]);
    } catch {
      /* corrupt / unavailable storage — start empty */
    }
    try {
      const raw = window.localStorage.getItem(VIZ_KEY);
      if (raw) {
        const viz = JSON.parse(raw) as {
          colorMode?: ColorMode;
          hidden?: string[];
        };
        // Validate the stored colour mode against the allowed literals — a
        // corrupt/hand-edited entry must not poison the typed state.
        if (viz.colorMode === "type" || viz.colorMode === "regime") {
          setColorMode(viz.colorMode);
        }
        if (Array.isArray(viz.hidden)) setHiddenCategories(viz.hidden);
      }
    } catch {
      /* corrupt / unavailable storage — start with defaults */
    }
  }, []);

  // Persist on change.
  React.useEffect(() => {
    try {
      window.localStorage.setItem(WATCHLIST_KEY, JSON.stringify(watchlist));
    } catch {
      /* storage unavailable — keep in-memory only */
    }
  }, [watchlist]);

  React.useEffect(() => {
    try {
      window.localStorage.setItem(
        VIZ_KEY,
        JSON.stringify({ colorMode, hidden: hiddenCategories })
      );
    } catch {
      /* storage unavailable — keep in-memory only */
    }
  }, [colorMode, hiddenCategories]);

  const watchSet = React.useMemo(() => new Set(watchlist), [watchlist]);
  const hiddenSet = React.useMemo(
    () => new Set(hiddenCategories),
    [hiddenCategories]
  );

  const value = React.useMemo<CatalogViewContextValue>(
    () => ({
      countryFilter,
      setCountryFilter,
      constellationFilter,
      setConstellationFilter,
      watchlist,
      isWatched: (id: string) => watchSet.has(id),
      toggleWatch: (id: string) =>
        setWatchlist((prev) =>
          prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
        ),
      colorMode,
      setColorMode,
      hiddenCategories,
      isCategoryHidden: (key: string) => hiddenSet.has(key),
      toggleCategory: (key: string) =>
        setHiddenCategories((prev) =>
          prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]
        ),
    }),
    [
      countryFilter,
      constellationFilter,
      watchlist,
      watchSet,
      colorMode,
      hiddenCategories,
      hiddenSet,
    ]
  );

  return (
    <CatalogViewContext.Provider value={value}>
      {children}
    </CatalogViewContext.Provider>
  );
}

export function useCatalogView(): CatalogViewContextValue {
  const ctx = React.useContext(CatalogViewContext);
  if (ctx === null) {
    throw new Error("useCatalogView must be used within a CatalogViewProvider");
  }
  return ctx;
}
