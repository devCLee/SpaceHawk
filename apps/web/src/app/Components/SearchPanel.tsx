"use client";

// Catalog search (#9a) + parametric find-sat (#9b).
//   - Text / NORAD / int'l-designator + type + country query → engine /catalog
//     via the BFF (#9a).
//   - Orbit-regime / inclination / period / eccentricity filters applied
//     client-side over the result set, derived from each candidate's TLE (#9b).
// Clicking a result selects it (shared context) → globe highlights + sidebar.

import React from "react";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { deriveOrbitParams, type OrbitRegime } from "../utils/sgp4FromTle";
import { useApiQuery } from "@/lib/api/useApiQuery";
import { queryKeys } from "@/lib/api/queryKeys";
import type { CatalogObject, CatalogQuery } from "@/lib/orbital-engine";
import * as s from "./panelStyles";

const RESULT_LIMIT = 1000;
const DEBOUNCE_MS = 300;

const REGIMES: Array<OrbitRegime | ""> = ["", "LEO", "MEO", "GEO", "HEO"];
const TYPES = ["", "PAYLOAD", "ROCKET BODY", "DEBRIS"];

function num(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export const SearchPanel: React.FunctionComponent = () => {
  const { setSelectedId } = useSelectedSatellite();

  const [q, setQ] = React.useState("");
  const [objectType, setObjectType] = React.useState("");
  const [country, setCountry] = React.useState("");
  // Parametric (find-sat) controls.
  const [regime, setRegime] = React.useState<OrbitRegime | "">("");
  const [inclMin, setInclMin] = React.useState("");
  const [inclMax, setInclMax] = React.useState("");
  const [periodMin, setPeriodMin] = React.useState("");
  const [periodMax, setPeriodMax] = React.useState("");
  const [eccMax, setEccMax] = React.useState("");

  // Debounce the server-side query inputs (text/type/country). setState lives
  // in the timeout callback, not synchronously in the effect body.
  const [debounced, setDebounced] = React.useState({
    q: "",
    objectType: "",
    country: "",
  });
  React.useEffect(() => {
    const handle = window.setTimeout(
      () =>
        setDebounced({
          q: q.trim(),
          objectType,
          country: country.trim().toUpperCase(),
        }),
      DEBOUNCE_MS
    );
    return () => window.clearTimeout(handle);
  }, [q, objectType, country]);

  const params: CatalogQuery = {
    limit: RESULT_LIMIT,
    q: debounced.q || undefined,
    object_type: debounced.objectType || undefined,
    country_code: debounced.country || undefined,
  };

  const {
    data: results = [],
    isLoading,
    isError,
  } = useApiQuery<CatalogObject[]>({
    queryKey: queryKeys.catalog(params),
    url: "/api/catalog",
    options: { params, keepPreviousData: true },
  });

  // Client-side parametric filter over the results.
  const filtered = React.useMemo(() => {
    const iMin = num(inclMin);
    const iMax = num(inclMax);
    const pMin = num(periodMin);
    const pMax = num(periodMax);
    const eMax = num(eccMax);
    const parametric =
      regime !== "" ||
      iMin !== null ||
      iMax !== null ||
      pMin !== null ||
      pMax !== null ||
      eMax !== null;
    if (!parametric) return results;

    return results.filter((r) => {
      if (!r.tle_line1 || !r.tle_line2) return false;
      const o = deriveOrbitParams(r.tle_line1, r.tle_line2);
      if (o === null) return false;
      if (regime !== "" && o.regime !== regime) return false;
      if (iMin !== null && o.inclinationDeg < iMin) return false;
      if (iMax !== null && o.inclinationDeg > iMax) return false;
      if (pMin !== null && o.periodMin < pMin) return false;
      if (pMax !== null && o.periodMin > pMax) return false;
      if (eMax !== null && o.eccentricity > eMax) return false;
      return true;
    });
  }, [results, regime, inclMin, inclMax, periodMin, periodMax, eccMax]);

  return (
    <div style={s.panel}>
      <div style={s.panelHeader}>
        <span style={s.panelTitle}>Catalog Search</span>
        <span style={s.muted}>{isLoading ? "…" : filtered.length}</span>
      </div>
      <div style={s.panelBody}>
        <input
          style={s.input}
          placeholder="Name / NORAD / int'l designator"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <div style={{ display: "flex", gap: 8 }}>
          <select
            style={s.input}
            value={objectType}
            onChange={(e) => setObjectType(e.target.value)}
          >
            {TYPES.map((t) => (
              <option key={t || "any"} value={t}>
                {t || "Any type"}
              </option>
            ))}
          </select>
          <input
            style={s.input}
            placeholder="Country"
            value={country}
            onChange={(e) => setCountry(e.target.value)}
          />
        </div>

        <details>
          <summary style={{ ...s.muted, cursor: "pointer" }}>
            Find-sat (parametric)
          </summary>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
            <select
              style={s.input}
              value={regime}
              onChange={(e) => setRegime(e.target.value as OrbitRegime | "")}
            >
              {REGIMES.map((r) => (
                <option key={r || "any"} value={r}>
                  {r || "Any regime"}
                </option>
              ))}
            </select>
            <div style={{ display: "flex", gap: 6 }}>
              <input style={s.input} placeholder="incl min°" value={inclMin} onChange={(e) => setInclMin(e.target.value)} />
              <input style={s.input} placeholder="incl max°" value={inclMax} onChange={(e) => setInclMax(e.target.value)} />
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <input style={s.input} placeholder="period min" value={periodMin} onChange={(e) => setPeriodMin(e.target.value)} />
              <input style={s.input} placeholder="period max" value={periodMax} onChange={(e) => setPeriodMax(e.target.value)} />
            </div>
            <input style={s.input} placeholder="ecc max" value={eccMax} onChange={(e) => setEccMax(e.target.value)} />
          </div>
        </details>

        {isLoading && <p style={s.muted}>Searching…</p>}
        {isError && <p style={s.error}>Search unavailable.</p>}
        {!isLoading && !isError && filtered.length === 0 && (
          <p style={s.muted}>No matches.</p>
        )}

        <ul style={s.list}>
          {filtered.map((r) => (
            <li
              key={r.object_id}
              style={s.listItem}
              onClick={() => setSelectedId(r.object_id)}
              onMouseEnter={(e) =>
                (e.currentTarget.style.background = "rgba(255,255,255,0.08)")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.background = "transparent")
              }
            >
              <span>{r.object_name}</span>
              <span style={s.muted}>{r.norad_cat_id ?? ""}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export default SearchPanel;
