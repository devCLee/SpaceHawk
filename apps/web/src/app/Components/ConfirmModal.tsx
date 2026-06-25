"use client";

// Lightweight confirmation dialog. No dependency / portal — a fixed full-screen
// overlay rendered inline by the caller (the dashboard panels). Click the
// backdrop or press Escape to cancel; the confirm button runs the action. Used
// by the country filter's bulk add/remove-to-watchlist flow (#9d/#9f).

import React from "react";
import { t } from "@/lib/i18n/t";

export const ConfirmModal: React.FunctionComponent<{
  title: string;
  message: string;
  /** Override the confirm button copy (defaults to the generic "확인"). */
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}> = ({ title, message, confirmLabel, onConfirm, onCancel }) => {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div style={styles.overlay} onClick={onCancel} role="presentation">
      <div
        style={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={styles.title}>{title}</div>
        <p style={styles.message} className="break-keep">
          {message}
        </p>
        <div style={styles.actions}>
          <button type="button" style={styles.cancel} onClick={onCancel}>
            {t("common.cancel")}
          </button>
          <button type="button" style={styles.confirm} onClick={onConfirm}>
            {confirmLabel ?? t("common.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmModal;

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed",
    inset: 0,
    zIndex: 1000,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "rgba(0, 0, 0, 0.55)",
  },
  modal: {
    width: 320,
    maxWidth: "calc(100vw - 32px)",
    background: "rgba(8, 12, 20, 0.98)",
    border: "1px solid rgba(255,255,255,0.14)",
    borderRadius: 8,
    boxShadow: "0 12px 40px rgba(0,0,0,0.55)",
    color: "#e6edf3",
    fontFamily: "system-ui, sans-serif",
    padding: "16px 18px",
  },
  title: {
    fontSize: 14,
    fontWeight: 600,
    letterSpacing: "0.02em",
    marginBottom: 8,
  },
  message: {
    fontSize: 13,
    lineHeight: 1.5,
    color: "#c4d0dc",
    margin: "0 0 16px",
  },
  actions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: 8,
  },
  cancel: {
    padding: "6px 14px",
    borderRadius: 4,
    border: "1px solid rgba(255,255,255,0.18)",
    background: "transparent",
    color: "#c4d0dc",
    fontSize: 13,
    cursor: "pointer",
  },
  confirm: {
    padding: "6px 14px",
    borderRadius: 4,
    border: "1px solid rgba(0, 180, 220, 0.6)",
    background: "rgba(0, 180, 220, 0.22)",
    color: "#e6edf3",
    fontSize: 13,
    cursor: "pointer",
  },
};
