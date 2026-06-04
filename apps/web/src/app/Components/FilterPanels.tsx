"use client";

// Countries (#9d), constellations (#9e), and watchlist (#9f) panels. Each
// drives the shared catalog-view state; the globe recolours accordingly.

import React from "react";
import CollapsiblePanel from "./CollapsiblePanel";
import { useCatalogView } from "../context/CatalogViewContext";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { countryName } from "../data/countries";
import { CONSTELLATIONS } from "../data/constellations";
import { useApiQuery } from "@/lib/api/useApiQuery";
import { queryKeys } from "@/lib/api/queryKeys";
import type { CatalogObject } from "@/lib/orbital-engine";
import * as s from "./panelStyles";

const AGG_LIMIT = 5000;

function selectableRow(active: boolean): React.CSSProperties {
  return {
    ...s.listItem,
    background: active ? "rgba(0, 180, 220, 0.18)" : "transparent",
  };
}

export const CountriesPanel: React.FunctionComponent = () => {
  const { countryFilter, setCountryFilter } = useCatalogView();
  const {
    data: rows = [],
    isLoading,
    isError,
  } = useApiQuery<CatalogObject[]>({
    queryKey: queryKeys.catalog({ limit: AGG_LIMIT }),
    url: "/api/catalog",
    options: { params: { limit: AGG_LIMIT } },
  });

  const counts = React.useMemo<Array<[string, number]>>(() => {
    const tally = new Map<string, number>();
    for (const r of rows) {
      const code = r.country_code ?? "—";
      tally.set(code, (tally.get(code) ?? 0) + 1);
    }
    return [...tally.entries()].sort((a, b) => b[1] - a[1]);
  }, [rows]);

  return (
    <CollapsiblePanel title="Countries">
      {isLoading && <p style={s.muted}>Loading…</p>}
      {isError && <p style={s.error}>Catalog unavailable.</p>}
      {countryFilter && (
        <button
          type="button"
          style={s.input}
          onClick={() => setCountryFilter(null)}
        >
          Clear filter
        </button>
      )}
      <ul style={s.list}>
        {counts.map(([code, n]) => (
          <li
            key={code}
            style={selectableRow(countryFilter === code)}
            onClick={() =>
              setCountryFilter(countryFilter === code ? null : code)
            }
          >
            <span>{countryName(code)}</span>
            <span style={s.muted}>{n}</span>
          </li>
        ))}
      </ul>
    </CollapsiblePanel>
  );
};

export const ConstellationsPanel: React.FunctionComponent = () => {
  const { constellationFilter, setConstellationFilter } = useCatalogView();
  return (
    <CollapsiblePanel title="Constellations">
      {constellationFilter && (
        <button
          type="button"
          style={s.input}
          onClick={() => setConstellationFilter(null)}
        >
          Clear filter
        </button>
      )}
      <ul style={s.list}>
        {CONSTELLATIONS.map((c) => (
          <li
            key={c.key}
            style={selectableRow(constellationFilter === c.key)}
            onClick={() =>
              setConstellationFilter(
                constellationFilter === c.key ? null : c.key
              )
            }
          >
            <span>{c.label}</span>
          </li>
        ))}
      </ul>
    </CollapsiblePanel>
  );
};

export const WatchlistPanel: React.FunctionComponent = () => {
  const { watchlist, toggleWatch } = useCatalogView();
  const { setSelectedId } = useSelectedSatellite();
  return (
    <CollapsiblePanel title={`Watchlist (${watchlist.length})`}>
      {watchlist.length === 0 && (
        <p style={s.muted}>
          No watched objects. Open an object and tap ☆ to watch it.
        </p>
      )}
      <ul style={s.list}>
        {watchlist.map((id) => (
          <li key={id} style={s.listItem}>
            <span
              style={{ cursor: "pointer" }}
              onClick={() => setSelectedId(id)}
            >
              {id}
            </span>
            <span
              style={{ cursor: "pointer", color: "#ff6b6b" }}
              onClick={() => toggleWatch(id)}
              role="button"
              aria-label={`Remove ${id} from watchlist`}
            >
              ✕
            </span>
          </li>
        ))}
      </ul>
    </CollapsiblePanel>
  );
};
