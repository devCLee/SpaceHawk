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
    <CollapsiblePanel title="Conjunctions">
      {isLoading && <p style={s.muted}>Loading…</p>}
      {isError && <p style={s.error}>Screening unavailable.</p>}
      {!isLoading && !isError && available === false && (
        <p style={s.muted}>
          Conjunction screening lands in Stage 4. This panel will list ranked
          conjunctions once the screening service is online.
        </p>
      )}
      {!isLoading && !isError && available && (
        <>
          <select
            style={s.input}
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
          >
            <option value="tca">Sort: time of closest approach</option>
            <option value="miss">Sort: miss distance</option>
            <option value="pc">Sort: probability</option>
          </select>
          {sorted.length === 0 ? (
            <p style={s.muted}>No conjunctions.</p>
          ) : (
            <ul style={s.list}>
              {sorted.map((c) => (
                <li
                  key={c.id}
                  style={s.listItem}
                  onClick={() => setSelectedId(c.primary_object_id)}
                >
                  <span>
                    {c.primary_name} ↔ {c.secondary_name}
                  </span>
                  <span style={{ color: SEVERITY_COLOR[c.severity] }}>
                    {c.miss_distance_km.toFixed(1)} km
                  </span>
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
