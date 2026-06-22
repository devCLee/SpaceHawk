// Behavioral coverage for the notification bell + the watchlist notification
// category. Mocks the app-global hooks Header reads (router, auth, globe
// controls, alert stream, catalog) so the bell renders without a real Cesium
// viewer or network, but keeps the REAL CatalogViewProvider — the provider whose
// absence caused the original "useCatalogView must be used within a
// CatalogViewProvider" crash when AlertsPop mounted.

import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Header from "../Header";
import { CatalogViewProvider } from "../../context/CatalogViewContext";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/",
}));

vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({
    user: { username: "tester", role: "analyst" },
    isAdmin: false,
    refresh: vi.fn(),
  }),
}));

// active:true makes Header render the globe-view group + bell (normally gated on
// a registered Cesium viewer).
vi.mock("../../context/GlobeControlsContext", () => ({
  useGlobeControls: () => ({
    active: true,
    railOpen: true,
    toggleRail: vi.fn(),
    mode: "online",
    setMode: vi.fn(),
    sceneMode: "3D",
    setSceneMode: vi.fn(),
    imageryOpen: false,
    toggleImagery: vi.fn(),
    imageryAvailable: false,
  }),
}));

// One conjunction alert for the watchlisted object (ISS) so the watchlist
// category has something to show.
vi.mock("../../context/AlertsContext", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../context/AlertsContext")>();
  return {
    ...actual,
    useAlerts: () => ({
      history: [
        {
          id: 1,
          receivedAt: Date.now(),
          alert: {
            type: "conjunction",
            object_id: "1998-067A",
            object_name: "ISS (ZARYA)",
            severity: "HIGH",
            ts: new Date().toISOString(),
            message: "근접 경고",
          },
        },
      ],
      active: [],
      dismiss: vi.fn(),
    }),
  };
});

// Catalog index the bell uses to resolve each watchlist alert's owner + name.
vi.mock("@/lib/api/useCatalog", () => ({
  useCatalog: () => ({
    data: [
      { OBJECT_ID: "1998-067A", OBJECT_NAME: "ISS (ZARYA)", COUNTRY_CODE: "US" },
    ],
  }),
}));

beforeEach(() => {
  window.localStorage.clear();
});

function openBell() {
  render(
    <CatalogViewProvider>
      <Header />
    </CatalogViewProvider>
  );
  fireEvent.click(screen.getByRole("button", { name: "알림" }));
}

describe("Header notification bell", () => {
  it("opens the dropdown without throwing and shows the watchlist category tab", () => {
    openBell();
    // AlertsPop mounted (the component that called useCatalogView) — tabs render.
    expect(screen.getByRole("button", { name: "전체" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /관심 위성/ })
    ).toBeInTheDocument();
  });

  it("shows the country flag + satellite title for a watchlisted alert", async () => {
    // Seed the persisted watchlist so the ISS alert is categorized as watchlist.
    window.localStorage.setItem(
      "spacehawk.watchlist",
      JSON.stringify(["1998-067A"])
    );
    openBell();
    fireEvent.click(screen.getByRole("button", { name: /관심 위성/ }));

    expect(await screen.findByText("ISS (ZARYA)")).toBeInTheDocument();
    // country-flag-icons renders the US flag SVG with a localized title.
    expect(screen.getByTitle("United States")).toBeInTheDocument();
  });
});
