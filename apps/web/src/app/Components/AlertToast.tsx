"use client";

import React from "react";
import {
  useAlerts,
  accentFor,
  titleFor,
  TOAST_TTL_MS,
  type AlertRecord,
} from "@/app/context/AlertsContext";
import { t } from "@/lib/i18n/t";

// Horizontal drag distance (px) past which a swipe dismisses the toast.
const SWIPE_THRESHOLD = 80;

/**
 * Floating live-alert toasts over the globe. The alert stream, session history,
 * and the notification bell now live in AlertsContext + the unified Header; this
 * surface is only the transient heads-up toasts (swipe- or button-dismissable,
 * auto-clearing after a minute). It sits clear of the header bar — the bell that
 * used to share this column moved into the header, so toasts no longer collide
 * with the scene/imagery controls or the satellite info panel.
 */
export default function AlertToast() {
  const { active, dismiss } = useAlerts();

  return (
    <div
      style={{
        position: "fixed",
        top: 68,
        right: 12,
        zIndex: 20,
        width: 320,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
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
    const tm = window.setTimeout(() => beginRemove(1), TOAST_TTL_MS);
    return () => window.clearTimeout(tm);
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
        aria-label={t("notifications.dismiss")}
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
          `${alert.lat_deg.toFixed(2)}°, ${alert.lon_deg.toFixed(
            2
          )}° · ${alert.alt_km.toFixed(0)} km · `}
        {new Date(alert.ts).toLocaleTimeString("ko-KR")}
      </div>
    </div>
  );
}
