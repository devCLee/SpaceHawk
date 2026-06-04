// Shared dark-operational-theme styles for the dashboard control panels
// (search / filters / sensors / collisions). Inline-CSS to match the existing
// CesiumComponent / SatelliteInfoPanel style in this app.

import type React from "react";

export const panel: React.CSSProperties = {
  background: "rgba(8, 12, 20, 0.92)",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 6,
  color: "#e6edf3",
  fontSize: 13,
  fontFamily: "system-ui, sans-serif",
};

export const panelHeader: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "8px 10px",
  cursor: "pointer",
  userSelect: "none",
};

export const panelTitle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  color: "#cfd8e3",
};

export const panelBody: React.CSSProperties = {
  padding: "8px 10px",
  borderTop: "1px solid rgba(255,255,255,0.08)",
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

export const input: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  padding: "5px 8px",
  borderRadius: 4,
  border: "1px solid rgba(255,255,255,0.18)",
  background: "rgba(0,0,0,0.4)",
  color: "#e6edf3",
  fontSize: 13,
};

export const label: React.CSSProperties = {
  fontSize: 11,
  color: "#7d8da0",
  marginBottom: 2,
};

export const list: React.CSSProperties = {
  listStyle: "none",
  margin: 0,
  padding: 0,
  maxHeight: 240,
  overflowY: "auto",
};

export const listItem: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  gap: 8,
  padding: "4px 6px",
  borderRadius: 4,
  cursor: "pointer",
};

export const muted: React.CSSProperties = { color: "#7d8da0" };

export const error: React.CSSProperties = { color: "#ff6b6b" };
