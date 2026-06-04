"use client";

import React from "react";

interface RegionAlert {
  type: string;
  object_id: string;
  object_name?: string;
  lat_deg: number;
  lon_deg: number;
  alt_km: number;
  ts: string;
  message: string;
}

/**
 * Subscribes to the engine's alert stream (via the /api/alerts SSE proxy) and
 * surfaces the most recent alerts as a small operational panel. EventSource
 * auto-reconnects, so transient backend restarts recover on their own.
 */
export default function AlertToast() {
  const [alerts, setAlerts] = React.useState<RegionAlert[]>([]);

  React.useEffect(() => {
    const source = new EventSource("/api/alerts");
    source.addEventListener("alert", (event) => {
      try {
        const alert = JSON.parse((event as MessageEvent).data) as RegionAlert;
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
      {alerts.map((alert) => (
        <div
          key={`${alert.object_id}-${alert.ts}`}
          style={{
            background: "rgba(20,20,28,0.92)",
            border: "1px solid rgba(255,90,90,0.6)",
            borderRadius: 8,
            padding: "10px 12px",
            color: "#fff",
            fontSize: 13,
            boxShadow: "0 2px 10px rgba(0,0,0,0.4)",
          }}
        >
          <div style={{ fontWeight: 600, color: "#ff7a7a" }}>Region entry</div>
          <div>{alert.message}</div>
          <div style={{ opacity: 0.7, fontSize: 11, marginTop: 4 }}>
            {alert.lat_deg.toFixed(2)}°, {alert.lon_deg.toFixed(2)}° ·{" "}
            {alert.alt_km.toFixed(0)} km · {new Date(alert.ts).toLocaleTimeString()}
          </div>
        </div>
      ))}
    </div>
  );
}
