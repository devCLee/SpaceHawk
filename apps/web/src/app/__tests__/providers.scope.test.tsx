// Regression guard for the bell crash: the notification bell lives in the global
// Header (root layout), so the watchlist/filter state it reads must be supplied
// app-wide. CatalogViewProvider used to be scoped to DashboardShell, one level
// below Header, so useCatalogView threw the moment the bell mounted. This test
// renders the REAL Providers tree and asserts useCatalogView resolves — if the
// provider is ever scoped back below the layout, this fails.

import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import Providers from "../providers";
import { useCatalogView } from "../context/CatalogViewContext";

function Probe() {
  const { watchlist } = useCatalogView();
  return <div data-testid="probe">watchlist:{watchlist.length}</div>;
}

describe("Providers", () => {
  it("supplies CatalogView context to anything in the app tree (incl. Header)", async () => {
    render(
      <Providers>
        <Probe />
      </Providers>
    );
    expect(await screen.findByTestId("probe")).toHaveTextContent("watchlist:0");
  });
});
