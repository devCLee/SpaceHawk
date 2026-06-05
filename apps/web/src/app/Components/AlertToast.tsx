"use client";

import React from "react";
import * as s from "./panelStyles";

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

// A received alert tagged with a client-side id + arrival time so toasts and
// the history dropdown can key off it and the time filter can window on it.
interface AlertRecord {
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
const TOAST_TTL_MS = 60_000;
// Horizontal drag distance (px) past which a swipe dismisses the toast.
const SWIPE_THRESHOLD = 80;
// Cap on the in-memory notification history (session-only; resets on reload).
const HISTORY_LIMIT = 500;
// Max live toasts shown at once.
const TOAST_LIMIT = 5;

const TIME_WINDOWS: { label: string; ms: number }[] = [
  { label: "1m", ms: 60_000 },
  { label: "30m", ms: 30 * 60_000 },
  { label: "1h", ms: 60 * 60_000 },
  { label: "12h", ms: 12 * 60 * 60_000 },
  { label: "1d", ms: 24 * 60 * 60_000 },
];

function accentFor(alert: LiveAlert): string {
  return alert.type === "conjunction"
    ? SEVERITY_COLOR[alert.severity ?? "MOD"] ?? "#ff7a7a"
    : "#ff7a7a";
}

function titleFor(alert: LiveAlert): string {
  return alert.type === "conjunction"
    ? `Conjunction${alert.severity ? ` · ${alert.severity}` : ""}`
    : "Region entry";
}

/**
 * Subscribes to the engine's alert stream (via the /api/alerts SSE proxy) and
 * surfaces alerts in two ways: transient live toasts (swipe- or button-
 * dismissable, auto-clearing after a minute) and a persistent notification bell
 * whose dropdown lists the full session history with a time-window filter.
 * EventSource auto-reconnects, so transient backend restarts recover on their
 * own. Durable triage of conjunction alerts still lives in the AlertCenter
 * panel; this is the heads-up + recent-history surface.
 */
export default function AlertToast() {
  const [history, setHistory] = React.useState<AlertRecord[]>([]);
  const [active, setActive] = React.useState<AlertRecord[]>([]);
  const [open, setOpen] = React.useState(false);
  const [windowMs, setWindowMs] = React.useState(TIME_WINDOWS[2].ms); // 1h
  const idRef = React.useRef(0);

  React.useEffect(() => {
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
  }, []);

  const dismiss = React.useCallback((id: number) => {
    setActive((prev) => prev.filter((r) => r.id !== id));
  }, []);

  return (
    <div
      style={{
        // Below Cesium's top-right toolbar (the 2D/3D scene-mode picker + the
        // base-layer tile-imagery picker, nudged to top:48 inside the globe by
        // globals.css), so toasts no longer overlap those controls.
        position: "fixed",
        top: 152,
        right: 12,
        zIndex: 20,
        width: 320,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-label="Notifications"
          aria-expanded={open}
          style={{
            position: "relative",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 34,
            height: 34,
            borderRadius: 8,
            border: "1px solid rgba(255,255,255,0.18)",
            background: open ? "rgba(59,130,246,0.25)" : "rgba(8,12,20,0.92)",
            color: "#e6edf3",
            cursor: "pointer",
          }}
        >
          <BellIcon />
          {history.length > 0 && (
            <span
              style={{
                position: "absolute",
                top: -5,
                right: -5,
                minWidth: 16,
                height: 16,
                padding: "0 4px",
                borderRadius: 8,
                background: "#ff6b6b",
                color: "#fff",
                fontSize: 10,
                fontWeight: 600,
                lineHeight: "16px",
                textAlign: "center",
              }}
            >
              {history.length > 99 ? "99+" : history.length}
            </span>
          )}
        </button>
      </div>

      {open && (
        <HistoryPanel
          history={history}
          windowMs={windowMs}
          setWindowMs={setWindowMs}
        />
      )}

      {active.map((record) => (
        <Toast key={record.id} record={record} onDismiss={dismiss} />
      ))}
    </div>
  );
}

/**
 * A single live toast. Auto-dismisses after one minute, can be closed with the
 * delete (×) button, and supports a sonner-style horizontal swipe: drag past
 * the threshold to fling it off-screen, release short to snap back.
 */
function Toast({
  record,
  onDismiss,
}: {
  record: AlertRecord;
  onDismiss: (id: number) => void;
}) {
  const { alert } = record;
  const accent = accentFor(alert);
  const isConjunction = alert.type === "conjunction";

  const [dragX, setDragX] = React.useState(0);
  const [dragging, setDragging] = React.useState(false);
  const [removing, setRemoving] = React.useState(false);
  const startX = React.useRef<number | null>(null);

  const beginRemove = React.useCallback(
    (direction: number) => {
      setRemoving(true);
      setDragging(false);
      setDragX(direction * 400);
      window.setTimeout(() => onDismiss(record.id), 200);
    },
    [onDismiss, record.id]
  );

  // Auto-dismiss one minute after the toast mounts.
  React.useEffect(() => {
    const t = window.setTimeout(() => beginRemove(1), TOAST_TTL_MS);
    return () => window.clearTimeout(t);
  }, [beginRemove]);

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (removing) return;
    startX.current = e.clientX;
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (startX.current === null) return;
    setDragX(e.clientX - startX.current);
  };
  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (startX.current === null) return;
    const dx = e.clientX - startX.current;
    startX.current = null;
    setDragging(false);
    if (Math.abs(dx) > SWIPE_THRESHOLD) beginRemove(dx > 0 ? 1 : -1);
    else setDragX(0);
  };

  return (
    <div
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      style={{
        position: "relative",
        background: "rgba(20,20,28,0.92)",
        border: `1px solid ${accent}`,
        borderRadius: 8,
        padding: "10px 28px 10px 12px",
        color: "#fff",
        fontSize: 13,
        boxShadow: "0 2px 10px rgba(0,0,0,0.4)",
        touchAction: "pan-y",
        cursor: "grab",
        transform: `translateX(${dragX}px)`,
        opacity: removing ? 0 : Math.max(1 - Math.abs(dragX) / 300, 0.3),
        transition: dragging
          ? "none"
          : "transform 0.2s ease, opacity 0.2s ease",
      }}
    >
      <button
        type="button"
        aria-label="Dismiss notification"
        onPointerDown={(e) => e.stopPropagation()}
        onClick={() => beginRemove(1)}
        style={{
          position: "absolute",
          top: 6,
          right: 6,
          width: 18,
          height: 18,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 0,
          borderRadius: 4,
          border: "none",
          background: "transparent",
          color: "rgba(255,255,255,0.6)",
          fontSize: 15,
          lineHeight: 1,
          cursor: "pointer",
        }}
      >
        ×
      </button>
      <div style={{ fontWeight: 600, color: accent }}>{titleFor(alert)}</div>
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
}

/**
 * Notification history dropdown — lists every alert received this session,
 * filtered to a selectable time window (1m / 30m / 1h / 12h / 1d).
 */
function HistoryPanel({
  history,
  windowMs,
  setWindowMs,
}: {
  history: AlertRecord[];
  windowMs: number;
  setWindowMs: (ms: number) => void;
}) {
  // Snapshot the clock in an effect (Date.now() is impure in render) and tick
  // it once a second so the time-window filter stays live while the dropdown
  // is open — a "1m" view drops entries as they age out.
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const filtered = history.filter((r) => now - r.receivedAt <= windowMs);

  return (
    <div style={{ ...s.panel, width: "100%" }}>
      <div style={{ ...s.panelHeader, cursor: "default" }}>
        <span style={s.panelTitle}>Notifications</span>
      </div>
      <div style={s.panelBody}>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {TIME_WINDOWS.map((w) => {
            const isActive = w.ms === windowMs;
            return (
              <button
                key={w.label}
                type="button"
                onClick={() => setWindowMs(w.ms)}
                style={{
                  padding: "2px 8px",
                  borderRadius: 4,
                  border: `1px solid ${isActive ? "#3b82f6" : "rgba(255,255,255,0.18)"}`,
                  background: isActive
                    ? "rgba(59,130,246,0.25)"
                    : "rgba(255,255,255,0.06)",
                  color: "#e6edf3",
                  fontSize: 11,
                  cursor: "pointer",
                }}
              >
                {w.label}
              </button>
            );
          })}
        </div>

        {filtered.length === 0 ? (
          <p style={s.muted}>No alerts in this window.</p>
        ) : (
          <ul style={s.list}>
            {filtered.map((r) => (
              <li
                key={r.id}
                style={{
                  ...s.listItem,
                  cursor: "default",
                  flexDirection: "column",
                  alignItems: "stretch",
                  gap: 2,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 8,
                  }}
                >
                  <span style={{ fontWeight: 600, color: accentFor(r.alert) }}>
                    {titleFor(r.alert)}
                  </span>
                  <span style={{ ...s.muted, fontSize: 11 }}>
                    {new Date(r.receivedAt).toLocaleTimeString()}
                  </span>
                </div>
                <span>{r.alert.message}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function BellIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}
