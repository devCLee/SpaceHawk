"use client";

// Countries (#9d), constellations (#9e), and watchlist (#9f) panels. Each
// drives the shared catalog-view state; the globe recolours accordingly.

import React from "react";
import * as Flags from "country-flag-icons/react/3x2";
import CollapsiblePanel from "./CollapsiblePanel";
import ConfirmModal from "./ConfirmModal";
import { useCatalogView } from "../context/CatalogViewContext";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { countryName, countryISO } from "../data/countries";
import { CONSTELLATIONS } from "../data/constellations";
import { useCatalog } from "@/lib/api/useCatalog";
import * as s from "./panelStyles";
import { t } from "@/lib/i18n/t";

type FlagComponent = React.FC<
  React.SVGProps<SVGSVGElement> & { title?: string }
>;

const flagStyle: React.CSSProperties = {
  width: 18,
  height: 13,
  borderRadius: 2,
  flexShrink: 0,
  boxShadow: "0 0 0 1px rgba(255,255,255,0.12)",
};

/** Resolve the country-flag-icons SVG for a Space-Track owner code, or null. */
function flagFor(code: string | null | undefined): FlagComponent | null {
  const iso = countryISO(code);
  if (!iso) return null;
  return (Flags as unknown as Record<string, FlagComponent>)[iso] ?? null;
}

const watchBtn: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: 18,
  height: 18,
  borderRadius: 4,
  border: "1px solid rgba(255,255,255,0.2)",
  background: "rgba(0,0,0,0.3)",
  color: "#c4d0dc",
  fontSize: 13,
  lineHeight: 1,
  cursor: "pointer",
};

function selectableRow(active: boolean): React.CSSProperties {
  return {
    ...s.listItem,
    background: active ? "rgba(0, 180, 220, 0.18)" : "transparent",
  };
}

export const CountriesPanel: React.FunctionComponent = () => {
  const {
    countryFilter,
    setCountryFilter,
    addManyToWatch,
    removeManyFromWatch,
  } = useCatalogView();
  // Counts derive from the same catalog the globe already loaded (shared React
  // Query cache) — no separate aggregate fetch.
  const { data: catalog = [], isLoading, isError } = useCatalog();

  // Group the watch ids (#9f) by owner code so the +/- buttons can add or remove
  // a whole country in one bulk update. Counts come straight off these groups.
  const idsByCountry = React.useMemo(() => {
    const map = new Map<string, string[]>();
    for (const r of catalog) {
      const id = r.OBJECT_ID ?? r.OBJECT_NAME;
      if (!id) continue;
      const code = r.COUNTRY_CODE ?? "—";
      const arr = map.get(code);
      if (arr) arr.push(id);
      else map.set(code, [id]);
    }
    return map;
  }, [catalog]);

  const counts = React.useMemo<Array<[string, number]>>(
    () =>
      [...idsByCountry.entries()]
        .map(([code, ids]): [string, number] => [code, ids.length])
        .sort((a, b) => b[1] - a[1]),
    [idsByCountry]
  );

  // The pending bulk action awaiting confirmation in the modal.
  const [pending, setPending] = React.useState<{
    code: string;
    mode: "add" | "remove";
  } | null>(null);

  const confirmPending = () => {
    if (!pending) return;
    const ids = idsByCountry.get(pending.code) ?? [];
    if (pending.mode === "add") addManyToWatch(ids);
    else removeManyFromWatch(ids);
    setPending(null);
  };

  return (
    <CollapsiblePanel title={t("countries.title")}>
      {isLoading && <p style={s.muted}>{t("common.loading")}</p>}
      {isError && <p style={s.error}>{t("countries.unavailable")}</p>}
      {countryFilter && (
        <button
          type="button"
          style={s.input}
          onClick={() => setCountryFilter(null)}
        >
          {t("common.clearFilter")}
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
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={s.muted}>{n}</span>
              <span
                role="button"
                aria-label={t("countries.addWatch", {
                  country: countryName(code),
                })}
                title={t("countries.addWatch", { country: countryName(code) })}
                style={watchBtn}
                onClick={(e) => {
                  e.stopPropagation();
                  setPending({ code, mode: "add" });
                }}
              >
                +
              </span>
              <span
                role="button"
                aria-label={t("countries.removeWatch", {
                  country: countryName(code),
                })}
                title={t("countries.removeWatch", {
                  country: countryName(code),
                })}
                style={watchBtn}
                onClick={(e) => {
                  e.stopPropagation();
                  setPending({ code, mode: "remove" });
                }}
              >
                −
              </span>
            </span>
          </li>
        ))}
      </ul>

      {pending && (
        <ConfirmModal
          title={t(
            pending.mode === "add"
              ? "countries.addTitle"
              : "countries.removeTitle"
          )}
          message={t(
            pending.mode === "add"
              ? "countries.addConfirm"
              : "countries.removeConfirm",
            {
              country: countryName(pending.code),
              n: idsByCountry.get(pending.code)?.length ?? 0,
            }
          )}
          onConfirm={confirmPending}
          onCancel={() => setPending(null)}
        />
      )}
    </CollapsiblePanel>
  );
};

export const ConstellationsPanel: React.FunctionComponent = () => {
  const { constellationFilter, setConstellationFilter } = useCatalogView();
  return (
    <CollapsiblePanel title={t("constellations.title")}>
      {constellationFilter && (
        <button
          type="button"
          style={s.input}
          onClick={() => setConstellationFilter(null)}
        >
          {t("common.clearFilter")}
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
  // Same shared catalog cache the country panel uses — index it by watch id so
  // each watchlist row can show the object's name (title) and owner flag.
  const { data: catalog = [] } = useCatalog();

  const byId = React.useMemo(() => {
    const m = new Map<string, { name: string; code: string | null }>();
    for (const r of catalog) {
      const id = r.OBJECT_ID ?? r.OBJECT_NAME;
      if (id) m.set(id, { name: r.OBJECT_NAME ?? id, code: r.COUNTRY_CODE ?? null });
    }
    return m;
  }, [catalog]);

  return (
    <CollapsiblePanel title={t("watchlist.title", { n: watchlist.length })}>
      {watchlist.length === 0 && (
        <p style={s.muted}>{t("watchlist.empty")}</p>
      )}
      <ul style={s.list}>
        {watchlist.map((id) => {
          const meta = byId.get(id);
          const title = meta?.name ?? id;
          const Flag = flagFor(meta?.code);
          return (
            <li key={id} style={s.listItem}>
              <span
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  minWidth: 0,
                  cursor: "pointer",
                }}
                onClick={() => setSelectedId(id)}
              >
                {Flag ? (
                  <Flag title={countryName(meta?.code)} style={flagStyle} />
                ) : (
                  <span style={{ fontSize: 14, lineHeight: 1 }} aria-hidden>
                    🌐
                  </span>
                )}
                <span
                  style={{
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {title}
                </span>
              </span>
              <span
                style={{ cursor: "pointer", color: "#ff6b6b", flexShrink: 0 }}
                onClick={() => toggleWatch(id)}
                role="button"
                aria-label={`Remove ${title} from watchlist`}
              >
                ✕
              </span>
            </li>
          );
        })}
      </ul>
    </CollapsiblePanel>
  );
};
