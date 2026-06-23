// Regression: 카탈로그 검색 must search the SAME catalog the globe renders, so every
// visualized object is findable — including snapshot-only objects (e.g. SKOR /
// Korean sats) that the live engine catalog may not carry. The old panel hit a
// separate engine-only endpoint (/api/catalog) with no snapshot fallback, so
// objects drawn from the bundled snapshot were invisible to search. The panel
// now filters the shared useCatalog() cache (/api/catalog/all) client-side.

import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SearchPanel from "../SearchPanel";
import { SelectedSatelliteProvider } from "../../context/SelectedSatelliteContext";
import { t } from "@/lib/i18n/t";

// Two-object catalog: one SKOR (snapshot-only owner code) + one US. Dummy TLE
// lines satisfy the TleObject shape; the text/country path under test never
// parses them (only the parametric find-sat path does).
const TLE1 = "1 29268U 06031A   26158.00000000  .00000100  00000-0  00000-0 0  9990";
const TLE2 = "2 29268  98.0000 100.0000 0001000  90.0000 270.0000 14.50000000 10000";

vi.mock("@/lib/api/useCatalog", () => ({
  useCatalog: () => ({
    data: [
      {
        OBJECT_ID: "2006-031A",
        OBJECT_NAME: "KOMPSAT-2 (ARIRANG-2)",
        NORAD_CAT_ID: 29268,
        COUNTRY_CODE: "SKOR",
        OBJECT_TYPE: "PAYLOAD",
        TLE_LINE1: TLE1,
        TLE_LINE2: TLE2,
      },
      {
        OBJECT_ID: "1998-067A",
        OBJECT_NAME: "ISS (ZARYA)",
        NORAD_CAT_ID: 25544,
        COUNTRY_CODE: "US",
        OBJECT_TYPE: "PAYLOAD",
        TLE_LINE1: TLE1,
        TLE_LINE2: TLE2,
      },
    ],
    isLoading: false,
    isError: false,
  }),
}));

function renderPanel() {
  return render(
    <SelectedSatelliteProvider>
      <SearchPanel />
    </SelectedSatelliteProvider>
  );
}

describe("SearchPanel — snapshot-only objects are searchable", () => {
  it("finds a SKOR object by country code", () => {
    renderPanel();
    // Both objects visible before filtering.
    expect(screen.getByText("KOMPSAT-2 (ARIRANG-2)")).toBeInTheDocument();
    expect(screen.getByText("ISS (ZARYA)")).toBeInTheDocument();

    const country = screen.getByPlaceholderText(t("search.placeholder.country"));
    fireEvent.change(country, { target: { value: "skor" } }); // case-insensitive

    expect(screen.getByText("KOMPSAT-2 (ARIRANG-2)")).toBeInTheDocument();
    expect(screen.queryByText("ISS (ZARYA)")).not.toBeInTheDocument();
  });

  it("finds the same SKOR object by name and by NORAD id", () => {
    renderPanel();
    const query = screen.getByPlaceholderText(t("search.placeholder.query"));

    fireEvent.change(query, { target: { value: "kompsat" } });
    expect(screen.getByText("KOMPSAT-2 (ARIRANG-2)")).toBeInTheDocument();
    expect(screen.queryByText("ISS (ZARYA)")).not.toBeInTheDocument();

    fireEvent.change(query, { target: { value: "29268" } });
    expect(screen.getByText("KOMPSAT-2 (ARIRANG-2)")).toBeInTheDocument();
  });
});
