"use client";

import React from "react";
import * as s from "./panelStyles";

/** A titled, collapsible card used by the left control-rail panels. */
export const CollapsiblePanel: React.FunctionComponent<{
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}> = ({ title, defaultOpen = false, children }) => {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div style={s.panel}>
      <div
        style={s.panelHeader}
        onClick={() => setOpen((o) => !o)}
        role="button"
        aria-expanded={open}
      >
        <span style={s.panelTitle}>{title}</span>
        <span style={s.muted}>{open ? "▾" : "▸"}</span>
      </div>
      {open && <div style={s.panelBody}>{children}</div>}
    </div>
  );
};

export default CollapsiblePanel;
