"use client";

// Countries (#9d), constellations (#9e), and watchlist (#9f) panels. Each
// drives the shared catalog-view state; the globe recolours accordingly.

import React from "react";
import CollapsiblePanel from "./CollapsiblePanel";
import { useCatalogView } from "../context/CatalogViewContext";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { countryName } from "../data/countries";
import { CONSTELLATIONS } from "../data/constellations";
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
  const [counts, setCounts] = React.useState<Array<[string, number]>>([]);
  const [status, setStatus] = React.useState<"loading" | "error" | "ready">(
    "loading"
  );

  React.useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/catalog?limit=${AGG_LIMIT}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`catalog fetch failed: ${res.status}`);
        return res.json() as Promise<CatalogObject[]>;
      })
      .then((rows) => {
        const tally = new Map<string, number>();
        for (const r of rows) {
          const code = r.country_code ?? "—";
          tally.set(code, (tally.get(code) ?? 0) + 1);
        }
        setCounts([...tally.entries()].sort((a, b) => b[1] - a[1]));
        setStatus("ready");
      })
      .catch((err) => {
        if (err.name !== "AbortError") setStatus("error");
      });
    return () => controller.abort();
  }, []);

  return (
    <CollapsiblePanel title="Countries">
      {status === "loading" && <p style={s.muted}>Loading…</p>}
      {status === "error" && <p style={s.error}>Catalog unavailable.</p>}
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
