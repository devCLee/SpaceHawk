"use client";

// 분석 이력 (analysis history) — full-page view of every analytical feature's
// stored history as client-side DataTables: 근접/충돌, 기동, 경보, RPO(경보
// type='rpo'), 행동 기준선, 궤도 이력. Each tab fetches once (limit 1000) via
// the BFF and sorts/filters/paginates in the browser. AuthGuard only gates the
// shell — the engine re-authorizes every call, and un-granted domains come back
// as `available: false` which renders the graceful "unavailable" state.

import { useState } from "react";
import AuthGuard from "@/app/Components/guards/AuthGuard";
import { useApiQuery } from "@/lib/api/useApiQuery";
import { queryKeys } from "@/lib/api/queryKeys";
import type {
  Alert,
  BaselinesResult,
  ConjunctionsResult,
  ManeuversResult,
} from "@/lib/orbital-engine";
import { t } from "@/lib/i18n/t";
import DataTable from "./DataTable";
import OrbitHistoryTab from "./OrbitHistoryTab";
import {
  alertColumns,
  baselineColumns,
  conjunctionColumns,
  maneuverColumns,
  rpoColumns,
} from "./columns";

const LIMIT = 1000;
const STALE_MS = 60_000;

const TABS = [
  "conjunctions",
  "maneuvers",
  "alerts",
  "rpo",
  "baselines",
  "orbit",
] as const;
type TabId = (typeof TABS)[number];

function Unavailable() {
  return <p className="text-sm text-slate-500">{t("history.unavailable")}</p>;
}

function HistoryView() {
  const [tab, setTab] = useState<TabId>("conjunctions");

  const conjunctions = useApiQuery<ConjunctionsResult>({
    queryKey: queryKeys.conjunctions(LIMIT),
    url: "/api/conjunctions",
    options: {
      params: { limit: LIMIT },
      enabled: tab === "conjunctions",
      staleTime: STALE_MS,
    },
  });
  const maneuvers = useApiQuery<ManeuversResult>({
    queryKey: queryKeys.maneuvers(undefined, LIMIT),
    url: "/api/maneuvers",
    options: {
      params: { limit: LIMIT },
      enabled: tab === "maneuvers",
      staleTime: STALE_MS,
    },
  });
  const alerts = useApiQuery<Alert[]>({
    queryKey: queryKeys.alerts(undefined, undefined, LIMIT),
    url: "/api/alerts/log",
    options: {
      params: { limit: LIMIT },
      enabled: tab === "alerts",
      staleTime: STALE_MS,
      retry: 0,
    },
  });
  const rpo = useApiQuery<Alert[]>({
    queryKey: queryKeys.alerts(undefined, "rpo", LIMIT),
    url: "/api/alerts/log",
    options: {
      params: { type: "rpo", limit: LIMIT },
      enabled: tab === "rpo",
      staleTime: STALE_MS,
      retry: 0,
    },
  });
  const baselines = useApiQuery<BaselinesResult>({
    queryKey: queryKeys.baselines(LIMIT),
    url: "/api/maneuvers/baselines",
    options: {
      params: { limit: LIMIT },
      enabled: tab === "baselines",
      staleTime: STALE_MS,
    },
  });

  return (
    <main className="min-h-screen bg-black px-8 pt-16 pb-8 text-slate-200">
      <h1 className="mb-4 text-2xl font-semibold">{t("history.title")}</h1>

      <div className="mb-4 flex flex-wrap gap-1 text-xs">
        {TABS.map((id) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`rounded border px-3 py-1.5 ${
              tab === id
                ? "border-slate-500 bg-slate-800 text-slate-100"
                : "border-slate-700 text-slate-400 hover:bg-slate-900"
            }`}
          >
            {t(`history.tab.${id}` as Parameters<typeof t>[0])}
          </button>
        ))}
      </div>

      {tab === "conjunctions" &&
        (conjunctions.data?.available === false ? (
          <Unavailable />
        ) : (
          <DataTable
            columns={conjunctionColumns}
            data={conjunctions.data?.conjunctions}
            isLoading={conjunctions.isLoading}
            isError={conjunctions.isError}
            searchPlaceholder={t("history.search")}
            initialSorting={[{ id: "tca", desc: false }]}
          />
        ))}

      {tab === "maneuvers" &&
        (maneuvers.data?.available === false ? (
          <Unavailable />
        ) : (
          <DataTable
            columns={maneuverColumns}
            data={maneuvers.data?.maneuvers}
            isLoading={maneuvers.isLoading}
            isError={maneuvers.isError}
            searchPlaceholder={t("history.search")}
            initialSorting={[{ id: "detected_epoch", desc: true }]}
          />
        ))}

      {tab === "alerts" && (
        <DataTable
          columns={alertColumns}
          data={alerts.data}
          isLoading={alerts.isLoading}
          isError={alerts.isError}
          searchPlaceholder={t("history.search")}
          initialSorting={[{ id: "created_at", desc: true }]}
        />
      )}

      {tab === "rpo" && (
        <DataTable
          columns={rpoColumns}
          data={rpo.data}
          isLoading={rpo.isLoading}
          isError={rpo.isError}
          searchPlaceholder={t("history.search")}
          initialSorting={[{ id: "created_at", desc: true }]}
        />
      )}

      {tab === "baselines" &&
        (baselines.data?.available === false ? (
          <Unavailable />
        ) : (
          <DataTable
            columns={baselineColumns}
            data={baselines.data?.baselines}
            isLoading={baselines.isLoading}
            isError={baselines.isError}
            searchPlaceholder={t("history.search")}
            initialSorting={[{ id: "last_epoch", desc: true }]}
          />
        ))}

      {tab === "orbit" && <OrbitHistoryTab />}
    </main>
  );
}

export default function HistoryPage() {
  return (
    <AuthGuard>
      <HistoryView />
    </AuthGuard>
  );
}
