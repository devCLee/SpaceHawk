"use client";

// Alert center (Stage 4). Lists the durable alert log with severity tiers and
// per-alert triage (acknowledge / dismiss); clicking an alert focuses its
// primary object on the globe. Conjunction alerts are produced by the engine's
// screening loop; this panel reads the queryable log (the live SSE toasts are
// handled separately by AlertToast).

import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import CollapsiblePanel from "./CollapsiblePanel";
import { useSelectedSatellite } from "../context/SelectedSatelliteContext";
import { useApiQuery } from "@/lib/api/useApiQuery";
import { queryKeys } from "@/lib/api/queryKeys";
import { http } from "@/lib/api/apiClient";
import type { Alert, AlertStatus, ConjunctionSeverity } from "@/lib/orbital-engine";
import * as s from "./panelStyles";
import { t } from "@/lib/i18n/t";
import { alertStatusLabel } from "@/lib/i18n/enums";

const SEVERITY_COLOR: Record<ConjunctionSeverity, string> = {
  LOW: "#7dd87d",
  MOD: "#ffd166",
  HIGH: "#ff6b6b",
};

const STATUS_FILTERS: AlertStatus[] = ["NEW", "ACK", "DISMISSED"];

const triageButton: React.CSSProperties = {
  padding: "2px 8px",
  borderRadius: 4,
  border: "1px solid rgba(255,255,255,0.18)",
  background: "rgba(255,255,255,0.06)",
  color: "#e6edf3",
  fontSize: 11,
  cursor: "pointer",
};

export const AlertCenter: React.FunctionComponent = () => {
  const { setSelectedId } = useSelectedSatellite();
  const queryClient = useQueryClient();
  const [status, setStatus] = React.useState<AlertStatus>("NEW");

  const { data, isLoading, isError } = useApiQuery<Alert[]>({
    queryKey: queryKeys.alerts(status),
    url: "/api/alerts/log",
    options: { params: { status }, refetchInterval: 15000 },
  });
  const alerts = React.useMemo<Alert[]>(() => data ?? [], [data]);

  const triage = useMutation({
    mutationFn: ({ id, next }: { id: string; next: "ACK" | "DISMISSED" }) =>
      http.post<Alert>(`/api/alerts/${encodeURIComponent(id)}/ack`, {
        status: next,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <CollapsiblePanel title={t("alertCenter.title")} defaultOpen>
      <select
        style={s.input}
        value={status}
        onChange={(e) => setStatus(e.target.value as AlertStatus)}
      >
        {STATUS_FILTERS.map((f) => (
          <option key={f} value={f}>
            {alertStatusLabel(f)}
          </option>
        ))}
      </select>

      {isLoading && <p style={s.muted}>{t("common.loading")}</p>}
      {isError && <p style={s.error}>{t("alertCenter.unavailable")}</p>}
      {!isLoading && !isError && alerts.length === 0 && (
        <p style={s.muted}>
          {t("alertCenter.none", { status: alertStatusLabel(status) })}
        </p>
      )}

      {alerts.length > 0 && (
        <ul style={s.list}>
          {alerts.map((a) => (
            <li
              key={a.id}
              style={{ ...s.listItem, flexDirection: "column", alignItems: "stretch", gap: 4 }}
            >
              <div
                style={{ display: "flex", justifyContent: "space-between", gap: 8 }}
                onClick={() => a.object_id && setSelectedId(a.object_id)}
              >
                <span>{a.message}</span>
                {a.severity && (
                  <span style={{ color: SEVERITY_COLOR[a.severity], fontWeight: 600 }}>
                    {a.severity}
                  </span>
                )}
              </div>
              {a.status === "NEW" && (
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    style={triageButton}
                    disabled={triage.isPending}
                    onClick={() => triage.mutate({ id: a.id, next: "ACK" })}
                  >
                    {t("alertCenter.acknowledge")}
                  </button>
                  <button
                    style={triageButton}
                    disabled={triage.isPending}
                    onClick={() => triage.mutate({ id: a.id, next: "DISMISSED" })}
                  >
                    {t("alertCenter.dismiss")}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </CollapsiblePanel>
  );
};

export default AlertCenter;
