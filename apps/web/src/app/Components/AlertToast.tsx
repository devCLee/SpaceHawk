"use client";

import React from "react";

// A live alert frame off the SSE channel. The channel now carries two shapes —
// the thin-slice region-entry alert and Stage-4 conjunction alerts — so fields
// are optional and rendering branches on `type`.
interface LiveAlert {
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

const SEVERITY_COLOR: Record<string, string> = {
  LOW: "#7dd87d",
  MOD: "#ffd166",
  HIGH: "#ff6b6b",
};

/**
 * Subscribes to the engine's alert stream (via the /api/alerts SSE proxy) and
 * surfaces the most recent alerts as a small operational panel. EventSource
 * auto-reconnects, so transient backend restarts recover on their own. Durable
 * triage of conjunction alerts lives in the AlertCenter panel; this is the
 * transient heads-up.
 */
export default function AlertToast() {
  const [alerts, setAlerts] = React.useState<LiveAlert[]>([]);

  React.useEffect(() => {
    const source = new EventSource("/api/alerts");
    source.addEventListener("alert", (event) => {
      try {
        const alert = JSON.parse((event as MessageEvent).data) as LiveAlert;
        setAlerts((prev) => [alert, ...prev].slice(0, 5));
      } catch {
        /* ignore malformed frames */
      }
    });
    return () => source.close();
  }, []);

  if (alerts.length === 0) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: 112,
        right: 12,
        zIndex: 20,
        width: 320,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      {alerts.map((alert, i) => {
        const isConjunction = alert.type === "conjunction";
        const accent = isConjunction
          ? SEVERITY_COLOR[alert.severity ?? "MOD"] ?? "#ff7a7a"
          : "#ff7a7a";
        return (
          <div
            key={`${alert.object_id ?? alert.type}-${alert.ts}-${i}`}
            style={{
              background: "rgba(20,20,28,0.92)",
              border: `1px solid ${accent}`,
              borderRadius: 8,
              padding: "10px 12px",
              color: "#fff",
              fontSize: 13,
              boxShadow: "0 2px 10px rgba(0,0,0,0.4)",
            }}
          >
            <div style={{ fontWeight: 600, color: accent }}>
              {isConjunction
                ? `Conjunction${alert.severity ? ` · ${alert.severity}` : ""}`
                : "Region entry"}
            </div>
            <div>{alert.message}</div>
            <div style={{ opacity: 0.7, fontSize: 11, marginTop: 4 }}>
              {!isConjunction &&
                alert.lat_deg != null &&
                alert.lon_deg != null &&
                alert.alt_km != null &&
                `${alert.lat_deg.toFixed(2)}°, ${alert.lon_deg.toFixed(2)}° · ${alert.alt_km.toFixed(0)} km · `}
              {new Date(alert.ts).toLocaleTimeString()}
            </div>
          </div>
        );
      })}
    </div>
  );
}
