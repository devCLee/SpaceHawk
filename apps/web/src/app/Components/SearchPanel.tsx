"use client";

// Catalog search (#9a) + parametric find-sat (#9b).
//   - Text / NORAD / int'l-designator + type + country query (#9a) and the
//     orbit-regime / inclination / period / eccentricity filters (#9b) are ALL
//     applied client-side over the shared globe catalog (useCatalog →
//     /api/catalog/all). Searching the same in-memory list the globe renders
//     guarantees every visualized object is findable — including snapshot-only
//     objects (e.g. SKOR) that the live engine catalog may not carry.
// Clicking a result selects it (shared context) → globe highlights + sidebar.

import React from "react";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { deriveOrbitParams, type OrbitRegime, type TleObject } from "../utils/sgp4FromTle";
import { useCatalog } from "@/lib/api/useCatalog";
import * as s from "./panelStyles";
import { t } from "@/lib/i18n/t";
import { objectTypeLabel } from "@/lib/i18n/enums";

// Max rows rendered. The filtered set can be the full ~15k catalog (empty
// query); cap the rendered list so we never mount thousands of <li>.
const RESULT_LIMIT = 1000;

const REGIMES: Array<OrbitRegime | ""> = ["", "LEO", "MEO", "GEO", "HEO"];
const TYPES = ["", "PAYLOAD", "ROCKET BODY", "DEBRIS"];

function num(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Globe id derivation — must match CesiumComponent so a clicked result selects
 *  the right point (entry.OBJECT_ID ?? entry.OBJECT_NAME). */
function entryId(r: TleObject): string | null {
  return r.OBJECT_ID ?? r.OBJECT_NAME ?? null;
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

  const { data: catalog = [], isLoading, isError } = useCatalog();

  // Stage 1 — cheap string filters (name / NORAD / int'l-designator, type,
  // country) over the full catalog. Runs first so the expensive SGP4 parametric
  // pass only sees the already-narrowed set.
  const textFiltered = React.useMemo(() => {
    const qq = q.trim().toLowerCase();
    const cc = country.trim().toUpperCase();
    if (!qq && !objectType && !cc) return catalog;
    return catalog.filter((r) => {
      if (objectType && (r.OBJECT_TYPE ?? "") !== objectType) return false;
      if (cc && (r.COUNTRY_CODE ?? "").toUpperCase() !== cc) return false;
      if (qq) {
        const name = (r.OBJECT_NAME ?? "").toLowerCase();
        const norad = r.NORAD_CAT_ID != null ? String(r.NORAD_CAT_ID) : "";
        const oid = (r.OBJECT_ID ?? "").toLowerCase();
        if (!name.includes(qq) && !norad.includes(qq) && !oid.includes(qq))
          return false;
      }
      return true;
    });
  }, [catalog, q, objectType, country]);

  // Stage 2 — orbit-regime / inclination / period / eccentricity filters,
  // derived from each candidate's TLE. SGP4 parse is costly, so it only runs
  // when a parametric control is set, and only over the stage-1 survivors.
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
    if (!parametric) return textFiltered;

    return textFiltered.filter((r) => {
      if (!r.TLE_LINE1 || !r.TLE_LINE2) return false;
      const o = deriveOrbitParams(r.TLE_LINE1, r.TLE_LINE2);
      if (o === null) return false;
      if (regime !== "" && o.regime !== regime) return false;
      if (iMin !== null && o.inclinationDeg < iMin) return false;
      if (iMax !== null && o.inclinationDeg > iMax) return false;
      if (pMin !== null && o.periodMin < pMin) return false;
      if (pMax !== null && o.periodMin > pMax) return false;
      if (eMax !== null && o.eccentricity > eMax) return false;
      return true;
    });
  }, [textFiltered, regime, inclMin, inclMax, periodMin, periodMax, eccMax]);

  const shown = filtered.slice(0, RESULT_LIMIT);

  return (
    <div style={s.panel}>
      <div style={s.panelHeader}>
        <span style={s.panelTitle}>{t("search.title")}</span>
        <span style={s.muted}>{isLoading ? "…" : filtered.length}</span>
      </div>
      <div style={s.panelBody}>
        <input
          style={s.input}
          placeholder={t("search.placeholder.query")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <div style={{ display: "flex", gap: 8 }}>
          <select
            style={s.input}
            value={objectType}
            onChange={(e) => setObjectType(e.target.value)}
          >
            {TYPES.map((type) => (
              <option key={type || "any"} value={type}>
                {objectTypeLabel(type)}
              </option>
            ))}
          </select>
          <input
            style={s.input}
            placeholder={t("search.placeholder.country")}
            value={country}
            onChange={(e) => setCountry(e.target.value)}
          />
        </div>

        <details>
          <summary style={{ ...s.muted, cursor: "pointer" }}>
            {t("search.findSat")}
          </summary>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
            <select
              style={s.input}
              value={regime}
              onChange={(e) => setRegime(e.target.value as OrbitRegime | "")}
            >
              {REGIMES.map((r) => (
                <option key={r || "any"} value={r}>
                  {r || t("search.regime.any")}
                </option>
              ))}
            </select>
            <div style={{ display: "flex", gap: 6 }}>
              <input style={s.input} placeholder={t("search.placeholder.inclMin")} value={inclMin} onChange={(e) => setInclMin(e.target.value)} />
              <input style={s.input} placeholder={t("search.placeholder.inclMax")} value={inclMax} onChange={(e) => setInclMax(e.target.value)} />
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <input style={s.input} placeholder={t("search.placeholder.periodMin")} value={periodMin} onChange={(e) => setPeriodMin(e.target.value)} />
              <input style={s.input} placeholder={t("search.placeholder.periodMax")} value={periodMax} onChange={(e) => setPeriodMax(e.target.value)} />
            </div>
            <input style={s.input} placeholder={t("search.placeholder.eccMax")} value={eccMax} onChange={(e) => setEccMax(e.target.value)} />
          </div>
        </details>

        {isLoading && <p style={s.muted}>{t("search.searching")}</p>}
        {isError && <p style={s.error}>{t("search.unavailable")}</p>}
        {!isLoading && !isError && filtered.length === 0 && (
          <p style={s.muted}>{t("search.noMatches")}</p>
        )}

        <ul style={s.list}>
          {shown.map((r, i) => {
            const id = entryId(r);
            return (
              <li
                key={id ?? `sat-${i}`}
                style={s.listItem}
                onClick={() => setSelectedId(id)}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background = "rgba(255,255,255,0.08)")
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.background = "transparent")
                }
              >
                <span>{r.OBJECT_NAME ?? id ?? ""}</span>
                <span style={s.muted}>{r.NORAD_CAT_ID ?? ""}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
};

export default SearchPanel;
