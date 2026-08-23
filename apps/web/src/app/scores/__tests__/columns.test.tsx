// 위협 점수 columns — the piece with logic beyond fetch wiring: null components
// render "—" (never 0), level classes color composite/level cells, and the
// accessorFn columns expose the nested component value so sorting works.

import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import DataTable from "../../history/DataTable";
import { LEVEL_CLASS, scoreColumns } from "../columns";
import type { ScoreItem, ScoreRaw } from "@/lib/orbital-engine";

const RAW: ScoreRaw = {
  max_confidence: 0.9,
  max_delta_v_m_s: 5.6,
  maneuver_count: 2,
  max_pc: 1e-4,
  min_miss_km: 0.8,
  severity: "HIGH",
  conjunction_count: 3,
  max_coplanarity: null,
  rpo_count: null,
  debris_risk_score: null,
  max_delta_v_sigma: null,
  novel_type: null,
  anomaly_count: null,
};

const ITEMS: ScoreItem[] = [
  {
    object_id: "SH:CAT:000000200",
    object_name: "THREAT SAT",
    composite: 76.9,
    level: "Critical",
    components: {
      maneuver: 0.9,
      conjunction: 0.75,
      rpo: null,
      debris: null,
      anomaly: null,
    },
    raw: RAW,
  },
  {
    object_id: "SH:CAT:000000300",
    object_name: "SHADOWER",
    composite: 60.0,
    level: "High",
    components: {
      maneuver: null,
      conjunction: null,
      rpo: 0.6,
      debris: null,
      anomaly: null,
    },
    raw: { ...RAW, max_coplanarity: 0.6, rpo_count: 1 },
  },
];

describe("scoreColumns", () => {
  it("renders composite colored by level and dashes for missing components", () => {
    render(<DataTable columns={scoreColumns} data={ITEMS} isLoading={false} />);

    const composite = screen.getByText("76.9");
    expect(composite.className).toContain(LEVEL_CLASS.Critical);
    expect(screen.getByText("Critical").className).toContain(
      LEVEL_CLASS.Critical
    );

    // THREAT SAT row: rpo/debris/anomaly are null → three dashes.
    const row = screen.getByText("THREAT SAT").closest("tr")!;
    expect(row.textContent!.match(/—/g)).toHaveLength(3);
  });

  it("exposes nested component values through accessorFn (sortable)", () => {
    const rpoCol = scoreColumns.find((c) => c.id === "rpo")!;
    expect("accessorFn" in rpoCol).toBe(true);
    const { accessorFn: accessor } = rpoCol as {
      accessorFn: (r: ScoreItem, i: number) => unknown;
    };
    expect(accessor(ITEMS[1], 1)).toBe(0.6);
    expect(accessor(ITEMS[0], 0)).toBeNull();
  });

  it("shows raw evidence in the component cell tooltip", () => {
    render(<DataTable columns={scoreColumns} data={ITEMS} isLoading={false} />);
    expect(screen.getByTitle(/coplanarity 0\.60/)).toHaveTextContent("0.60");
    expect(screen.getByTitle(/Pc 1\.00e-4/)).toHaveTextContent("0.75");
  });
});
