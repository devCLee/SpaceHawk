"use client";

// Catalog-view state shared between the control panels and the globe:
//   - country filter (#9d) and constellation filter (#9e) — the globe colours
//     matches and dims the rest;
//   - watchlist (#9f) — user-managed object-of-interest ids. The SERVER is the
//     source of truth (engine /watchlist, per-user via the session): on mount we
//     GET /api/watchlist and seed state; add/remove optimistically update local
//     state and POST/DELETE to /api/watchlist, reverting on failure. This keeps
//     the daily report (which reads the watchlist per owner_username) in sync
//     with what the user actually added. The globe marks watched objects and the
//     watchlist panel lists them. (Distinct from the RPO protected-asset list in
//     Stage 6, but a future backend list model can back both — dev-plan Stage 3.)
//   - visualization options (#viz) — the colour-by mode (object class / orbit
//     regime), the set of categories hidden from the globe, and the
//     watchlist-only toggle, persisted to localStorage so the analyst's chosen
//     view survives a reload. (Only watchlist MEMBERSHIP moved to the server; the
//     watchlistOnly filter is a pure client-side view preference.)

import React from "react";
import type { ColorMode } from "../data/visualization";

// Retained for the one-time migration of a pre-server (localStorage) watchlist.
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
  /** Bulk add (e.g. every satellite of one country) — already-watched ids are
   *  skipped so the operation is idempotent and preserves insertion order. */
  addManyToWatch: (ids: string[]) => void;
  /** Bulk remove — drops every given id from the watchlist in one update. */
  removeManyFromWatch: (ids: string[]) => void;
  /** Globe colour-by axis: object class or orbit regime. */
  colorMode: ColorMode;
  setColorMode: (mode: ColorMode) => void;
  /** Category keys hidden from the globe (under the active colour mode). */
  hiddenCategories: string[];
  isCategoryHidden: (key: string) => boolean;
  toggleCategory: (key: string) => void;
  /** When true, the globe shows only watchlisted objects (everything else is
   *  hidden). Persisted with the other viz options. */
  watchlistOnly: boolean;
  setWatchlistOnly: (v: boolean) => void;
}

const CatalogViewContext =
  React.createContext<CatalogViewContextValue | null>(null);

// --- Server sync helpers (client-side fetch to the same-origin BFF proxy) ---

/** GET the current user's watchlist. Returns null when the call fails (engine
 *  down, 401/403, or no browser fetch) so the caller can fall back gracefully. */
async function fetchServerWatchlist(): Promise<string[] | null> {
  if (typeof window === "undefined") return null;
  try {
    const res = await fetch("/api/watchlist", { cache: "no-store" });
    if (!res.ok) return null;
    const data = (await res.json()) as unknown;
    return Array.isArray(data) ? (data as string[]) : null;
  } catch {
    return null;
  }
}

/** POST one id to the watchlist. Resolves true on success, false on any failure
 *  (so callers can revert optimistic state). */
async function postServerWatchlist(id: string): Promise<boolean> {
  if (typeof window === "undefined") return false;
  try {
    const res = await fetch("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ object_id: id }),
      cache: "no-store",
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** DELETE one id from the watchlist. Resolves true on success, false otherwise. */
async function deleteServerWatchlist(id: string): Promise<boolean> {
  if (typeof window === "undefined") return false;
  try {
    const res = await fetch(`/api/watchlist/${encodeURIComponent(id)}`, {
      method: "DELETE",
      cache: "no-store",
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Read the legacy localStorage watchlist for the one-time migration. */
function readLocalWatchlist(): string[] {
  try {
    const raw = window.localStorage.getItem(WATCHLIST_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as string[]) : [];
  } catch {
    return [];
  }
}

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
  const [watchlistOnly, setWatchlistOnly] = React.useState(false);

  // Seed the watchlist from the server once on mount. If the server list is
  // empty AND a legacy localStorage watchlist exists, migrate those ids up
  // (best-effort POST) and seed from them — this preserves the user's existing
  // picks. The localStorage key is intentionally KEPT, not cleared: a failed
  // migration POST (offline / 401) would otherwise lose the picks, and the
  // migration is idempotent (once the server has the ids, the server list is
  // non-empty so the branch never runs again). The seed/migration are
  // client-only (guarded against SSR) and a post-mount setState (not a lazy
  // initializer) so server and first client render agree (no hydration mismatch).
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      const server = await fetchServerWatchlist();
      if (cancelled) return;
      if (server !== null && server.length > 0) {
        setWatchlist(server);
        return;
      }
      // Server empty (or unavailable) — fall back to the legacy localStorage
      // list and migrate it up.
      const local = readLocalWatchlist();
      if (local.length > 0) {
        setWatchlist(local);
        // Best-effort: push each id to the server. Failures are ignored (the
        // localStorage key stays, so a later load retries the migration).
        for (const id of local) {
          if (cancelled) return;
          void postServerWatchlist(id);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Load the persisted viz options once on mount. As with the watchlist seed,
  // this is a post-mount setState (not a lazy initializer) so the server ([])
  // and first client render agree — no hydration mismatch.
  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(VIZ_KEY);
      if (raw) {
        const viz = JSON.parse(raw) as {
          colorMode?: ColorMode;
          hidden?: string[];
          watchlistOnly?: boolean;
        };
        // Validate the stored colour mode against the allowed literals — a
        // corrupt/hand-edited entry must not poison the typed state.
        if (viz.colorMode === "type" || viz.colorMode === "regime") {
          // eslint-disable-next-line react-hooks/set-state-in-effect -- hydration-safe one-time load from localStorage
          setColorMode(viz.colorMode);
        }
        if (Array.isArray(viz.hidden)) setHiddenCategories(viz.hidden);
        if (typeof viz.watchlistOnly === "boolean") {
          setWatchlistOnly(viz.watchlistOnly);
        }
      }
    } catch {
      /* corrupt / unavailable storage — start with defaults */
    }
  }, []);

  // Persist the viz options (incl. the client-side watchlistOnly toggle) on
  // change. The watchlist membership itself is server-backed, so it is no longer
  // mirrored to localStorage here.
  React.useEffect(() => {
    try {
      window.localStorage.setItem(
        VIZ_KEY,
        JSON.stringify({ colorMode, hidden: hiddenCategories, watchlistOnly })
      );
    } catch {
      /* storage unavailable — keep in-memory only */
    }
  }, [colorMode, hiddenCategories, watchlistOnly]);

  const watchSet = React.useMemo(() => new Set(watchlist), [watchlist]);
  const hiddenSet = React.useMemo(
    () => new Set(hiddenCategories),
    [hiddenCategories]
  );

  // Optimistically add ids: update state now, POST each new id, and revert the
  // failures. Already-watched ids are skipped (idempotent, order-preserving).
  const addIds = React.useCallback((ids: string[]) => {
    setWatchlist((prev) => {
      const seen = new Set(prev);
      const added: string[] = [];
      const next = [...prev];
      for (const id of ids) {
        if (!seen.has(id)) {
          seen.add(id);
          next.push(id);
          added.push(id);
        }
      }
      for (const id of added) {
        void postServerWatchlist(id).then((ok) => {
          if (!ok) {
            console.warn(`watchlist add failed for ${id} — reverting`);
            setWatchlist((cur) => cur.filter((x) => x !== id));
          }
        });
      }
      return next;
    });
  }, []);

  // Optimistically remove ids: update state now, DELETE each removed id, and
  // re-add the failures.
  const removeIds = React.useCallback((ids: string[]) => {
    setWatchlist((prev) => {
      const drop = new Set(ids);
      const removed = prev.filter((x) => drop.has(x));
      for (const id of removed) {
        void deleteServerWatchlist(id).then((ok) => {
          if (!ok) {
            console.warn(`watchlist remove failed for ${id} — reverting`);
            setWatchlist((cur) => (cur.includes(id) ? cur : [...cur, id]));
          }
        });
      }
      return prev.filter((x) => !drop.has(x));
    });
  }, []);

  const value = React.useMemo<CatalogViewContextValue>(
    () => ({
      countryFilter,
      setCountryFilter,
      constellationFilter,
      setConstellationFilter,
      watchlist,
      isWatched: (id: string) => watchSet.has(id),
      toggleWatch: (id: string) =>
        watchSet.has(id) ? removeIds([id]) : addIds([id]),
      addManyToWatch: (ids: string[]) => addIds(ids),
      removeManyFromWatch: (ids: string[]) => removeIds(ids),
      colorMode,
      setColorMode,
      hiddenCategories,
      isCategoryHidden: (key: string) => hiddenSet.has(key),
      toggleCategory: (key: string) =>
        setHiddenCategories((prev) =>
          prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]
        ),
      watchlistOnly,
      setWatchlistOnly,
    }),
    [
      countryFilter,
      constellationFilter,
      watchlist,
      watchSet,
      addIds,
      removeIds,
      colorMode,
      hiddenCategories,
      hiddenSet,
      watchlistOnly,
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
