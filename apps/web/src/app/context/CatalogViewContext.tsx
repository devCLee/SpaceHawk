"use client";

// Catalog-view state shared between the control panels and the globe:
//   - country filter (#9d) and constellation filter (#9e) — the globe colours
//     matches and dims the rest;
//   - watchlist (#9f) — user-managed object-of-interest ids, persisted to
//     localStorage; the globe marks them and the watchlist panel lists them.
//     (Distinct from the RPO protected-asset list in Stage 6, but a future
//     backend list model can back both — dev-plan Stage 3.)

import React from "react";

const WATCHLIST_KEY = "spacehawk.watchlist";

interface CatalogViewContextValue {
  countryFilter: string | null;
  setCountryFilter: (code: string | null) => void;
  constellationFilter: string | null;
  setConstellationFilter: (key: string | null) => void;
  watchlist: string[];
  isWatched: (id: string) => boolean;
  toggleWatch: (id: string) => void;
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

  // Load the persisted watchlist once on mount. This is intentionally a
  // post-mount setState (not a lazy initializer): reading localStorage during
  // render would diverge between the server ([]) and the client, reintroducing
  // a hydration mismatch. Safe here — it runs once and is not a render loop.
  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(WATCHLIST_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- hydration-safe one-time load from localStorage
      if (raw) setWatchlist(JSON.parse(raw) as string[]);
    } catch {
      /* corrupt / unavailable storage — start empty */
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

  const watchSet = React.useMemo(() => new Set(watchlist), [watchlist]);

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
    }),
    [countryFilter, constellationFilter, watchlist, watchSet]
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
