"use client";

// Single owner of the live alert stream. Subscribes to the engine's alert SSE
// (via the /api/alerts proxy) once, while authenticated, and exposes both
// surfaces it feeds: the session `history` (the Header's notification bell +
// dropdown) and the transient `active` toasts (the floating AlertToasts).
//
// Splitting the subscription out of the old AlertToast lets the bell live in the
// unified Header while the toasts keep floating over the globe — both read the
// same stream, so there is exactly one EventSource.

import React from "react";
import { useAuth } from "@/app/context/AuthContext";
import { t } from "@/lib/i18n/t";

// The channel carries two shapes — the thin-slice region-entry alert and Stage-4
// conjunction alerts — so fields are optional and rendering branches on `type`.
export interface LiveAlert {
  type: string;
  object_id?: string;
  object_name?: string;
  severity?: "LOW" | "MOD" | "HIGH";
  lat_deg?: number;
  lon_deg?: number;
  alt_km?: number;
  ts: string;
  message: string;
}

// A received alert tagged with a client-side id + arrival time so toasts and the
// history dropdown can key off it and the time filter can window on it.
export interface AlertRecord {
  id: number;
  alert: LiveAlert;
  receivedAt: number;
}

const SEVERITY_COLOR: Record<string, string> = {
  LOW: "#7dd87d",
  MOD: "#ffd166",
  HIGH: "#ff6b6b",
};

// Live toasts auto-dismiss one minute after they arrive.
export const TOAST_TTL_MS = 60_000;
// Cap on the in-memory notification history (session-only; resets on reload).
const HISTORY_LIMIT = 500;
// Max live toasts shown at once.
const TOAST_LIMIT = 5;

export const TIME_WINDOWS: { label: string; ms: number }[] = [
  { label: "1m", ms: 60_000 },
  { label: "30m", ms: 30 * 60_000 },
  { label: "1h", ms: 60 * 60_000 },
  { label: "12h", ms: 12 * 60 * 60_000 },
  { label: "24h", ms: 24 * 60 * 60_000 },
];

export function accentFor(alert: LiveAlert): string {
  return alert.type === "conjunction"
    ? SEVERITY_COLOR[alert.severity ?? "MOD"] ?? "#ff7a7a"
    : "#ff7a7a";
}

export function titleFor(alert: LiveAlert): string {
  return alert.type === "conjunction"
    ? `${t("toast.conjunction")}${alert.severity ? ` · ${alert.severity}` : ""}`
    : t("toast.regionEntry");
}

interface AlertsValue {
  history: AlertRecord[];
  active: AlertRecord[];
  dismiss: (id: number) => void;
}

const AlertsContext = React.createContext<AlertsValue | null>(null);

export function AlertsProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [history, setHistory] = React.useState<AlertRecord[]>([]);
  const [active, setActive] = React.useState<AlertRecord[]>([]);
  const idRef = React.useRef(0);

  React.useEffect(() => {
    // The alert stream requires a session; only open it while authenticated so
    // the signin screen never opens a 401-looping EventSource.
    if (!user) return;
    const source = new EventSource("/api/alerts");
    source.addEventListener("alert", (event) => {
      try {
        const alert = JSON.parse((event as MessageEvent).data) as LiveAlert;
        const record: AlertRecord = {
          id: (idRef.current += 1),
          alert,
          receivedAt: Date.now(),
        };
        setHistory((prev) => [record, ...prev].slice(0, HISTORY_LIMIT));
        setActive((prev) => [record, ...prev].slice(0, TOAST_LIMIT));
      } catch {
        /* ignore malformed frames */
      }
    });
    return () => source.close();
  }, [user]);

  const dismiss = React.useCallback((id: number) => {
    setActive((prev) => prev.filter((r) => r.id !== id));
  }, []);

  const value = React.useMemo<AlertsValue>(
    () => ({ history, active, dismiss }),
    [history, active, dismiss]
  );

  return (
    <AlertsContext.Provider value={value}>{children}</AlertsContext.Provider>
  );
}

export function useAlerts(): AlertsValue {
  const ctx = React.useContext(AlertsContext);
  if (ctx === null) {
    throw new Error("useAlerts must be used within an AlertsProvider");
  }
  return ctx;
}
