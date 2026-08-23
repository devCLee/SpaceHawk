"use client";

// ⑥ 궤도 이력 tab — pick one object, list its gp_history element sets. The
// picker filters the shared useCatalog() cache client-side (same source and
// pattern as 카탈로그 검색, so every visualized object is findable), then the
// selected object's history loads via the BFF.

import { useMemo, useState } from "react";
import { useCatalog } from "@/lib/api/useCatalog";
import { useApiQuery } from "@/lib/api/useApiQuery";
import { queryKeys } from "@/lib/api/queryKeys";
import type { HistoryPoint } from "@/lib/orbital-engine";
import { t } from "@/lib/i18n/t";
import DataTable from "./DataTable";
import { historyPointColumns } from "./columns";

const MAX_MATCHES = 30;

export default function OrbitHistoryTab() {
  const { data: catalog } = useCatalog();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<{ id: string; name: string } | null>(
    null
  );

  const matches = useMemo(() => {
    const q = query.trim().toUpperCase();
    if (!q || !catalog) return [];
    return catalog
      .filter(
        (o) =>
          // gp_history is keyed by the canonical OBJECT_ID — snapshot-only
          // objects without one have no history to show, skip them.
          o.OBJECT_ID &&
          (o.OBJECT_NAME?.toUpperCase().includes(q) ||
            o.OBJECT_ID.toUpperCase().includes(q) ||
            String(o.NORAD_CAT_ID ?? "").includes(q))
      )
      .slice(0, MAX_MATCHES);
  }, [catalog, query]);

  const history = useApiQuery<HistoryPoint[]>({
    queryKey: queryKeys.objectHistory(selected?.id ?? ""),
    url: `/api/catalog/${encodeURIComponent(selected?.id ?? "")}/history`,
    options: { enabled: selected !== null, staleTime: 60_000, retry: 0 },
  });

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("history.objectSearch")}
          className="w-64 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200 placeholder:text-slate-600 focus:border-slate-500 focus:outline-none"
        />
        {selected && (
          <span className="text-xs text-slate-300">
            {selected.name}{" "}
            <span className="text-slate-500">({selected.id})</span>
          </span>
        )}
      </div>

      {query.trim() && (
        <ul className="mb-3 max-h-48 w-fit min-w-64 overflow-auto rounded border border-slate-800 text-xs">
          {matches.length === 0 ? (
            <li className="px-2 py-1.5 text-slate-500">
              {t("history.noMatches")}
            </li>
          ) : (
            matches.map((o) => (
              <li key={o.OBJECT_ID}>
                <button
                  onClick={() => {
                    setSelected({
                      id: o.OBJECT_ID!,
                      name: o.OBJECT_NAME ?? o.OBJECT_ID!,
                    });
                    setQuery("");
                  }}
                  className="flex w-full items-center justify-between gap-4 px-2 py-1.5 text-left text-slate-200 hover:bg-slate-800"
                >
                  <span>{o.OBJECT_NAME}</span>
                  <span className="text-slate-500">{o.NORAD_CAT_ID}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}

      {selected === null ? (
        <p className="text-sm text-slate-500">{t("history.pickObject")}</p>
      ) : (
        <DataTable
          columns={historyPointColumns}
          data={history.data}
          isLoading={history.isLoading}
          isError={history.isError}
          initialSorting={[{ id: "epoch", desc: true }]}
        />
      )}
    </div>
  );
}
