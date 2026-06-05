"use client";

// Conjunction browse & search (#9g). Sortable list of screened conjunctions
// with drill-down (selecting a row focuses the primary object on the globe).
// Backed by the Stage-4 screening service — until that lands, the panel shows a
// "screening pending" state (the /api/conjunctions BFF returns available:false).

import React from "react";
import CollapsiblePanel from "./CollapsiblePanel";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { useApiQuery } from "@/lib/api/useApiQuery";
import { queryKeys } from "@/lib/api/queryKeys";
import type {
  Conjunction,
  ConjunctionSeverity,
  ConjunctionsResult,
} from "@/lib/orbital-engine";
import * as s from "./panelStyles";
import { t } from "@/lib/i18n/t";

type SortKey = "tca" | "miss" | "pc";

const SEVERITY_COLOR: Record<ConjunctionSeverity, string> = {
  LOW: "#7dd87d",
  MOD: "#ffd166",
  HIGH: "#ff6b6b",
};

function sortConjunctions(rows: Conjunction[], key: SortKey): Conjunction[] {
  const copy = [...rows];
  if (key === "tca") {
    copy.sort((a, b) => a.tca.localeCompare(b.tca));
  } else if (key === "miss") {
    copy.sort((a, b) => a.miss_distance_km - b.miss_distance_km);
  } else {
    copy.sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0));
  }
  return copy;
}

export const CollisionsPanel: React.FunctionComponent = () => {
  const { setSelectedId } = useSelectedSatellite();
  const [sortKey, setSortKey] = React.useState<SortKey>("tca");

  const { data, isLoading, isError } = useApiQuery<ConjunctionsResult>({
    queryKey: queryKeys.conjunctions(),
    url: "/api/conjunctions",
  });
  const rows = React.useMemo<Conjunction[]>(
    () => data?.conjunctions ?? [],
    [data]
  );
  const available = data?.available ?? null;

  const sorted = React.useMemo(
    () => sortConjunctions(rows, sortKey),
    [rows, sortKey]
  );

  return (
    <CollapsiblePanel title={t("conjunctions.title")}>
      {isLoading && <p style={s.muted}>{t("common.loading")}</p>}
      {isError && <p style={s.error}>{t("conjunctions.unavailable")}</p>}
      {!isLoading && !isError && available === false && (
        <p style={s.muted}>{t("conjunctions.pending")}</p>
      )}
      {!isLoading && !isError && available && (
        <>
          <select
            style={s.input}
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
          >
            <option value="tca">{t("conjunctions.sort.tca")}</option>
            <option value="miss">{t("conjunctions.sort.miss")}</option>
            <option value="pc">{t("conjunctions.sort.pc")}</option>
          </select>
          {sorted.length === 0 ? (
            <p style={s.muted}>{t("conjunctions.none")}</p>
          ) : (
            <ul style={s.list}>
              {sorted.map((c) => (
                <li
                  key={c.id}
                  style={{ ...s.listItem, flexDirection: "column", alignItems: "stretch", gap: 2 }}
                  onClick={() => setSelectedId(c.primary_object_id)}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <span>
                      {c.primary_name} ↔ {c.secondary_name}
                    </span>
                    <span style={{ color: SEVERITY_COLOR[c.severity], fontWeight: 600 }}>
                      {c.severity}
                    </span>
                  </div>
                  <div style={{ ...s.muted, fontSize: 11, display: "flex", gap: 10 }}>
                    <span>{c.miss_distance_km.toFixed(2)} km</span>
                    <span>
                      Pc {c.probability != null ? c.probability.toExponential(1) : "n/a"}
                    </span>
                    <span>{new Date(c.tca).toLocaleString()}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </CollapsiblePanel>
  );
};

export default CollisionsPanel;
