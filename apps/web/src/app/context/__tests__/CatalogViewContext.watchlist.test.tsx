// Server-backed watchlist behavior (A2): the context seeds from /api/watchlist
// on mount, optimistically updates + POST/DELETEs on add/remove, reverts on a
// failed call, and migrates a legacy localStorage watchlist when the server is
// empty. fetch is mocked per-test (no live engine).

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor, cleanup } from "@testing-library/react";
import {
  CatalogViewProvider,
  useCatalogView,
} from "../CatalogViewContext";

type FetchMock = ReturnType<typeof vi.fn>;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderView() {
  return renderHook(() => useCatalogView(), {
    wrapper: ({ children }: { children: React.ReactNode }) => (
      <CatalogViewProvider>{children}</CatalogViewProvider>
    ),
  });
}

let fetchMock: FetchMock;

beforeEach(() => {
  window.localStorage.clear();
  fetchMock = vi.fn();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CatalogViewContext watchlist (server-backed)", () => {
  it("seeds the watchlist from GET /api/watchlist on mount", async () => {
    fetchMock.mockResolvedValue(jsonResponse(["SH:CAT:1", "SH:CAT:2"]));

    const { result } = renderView();
    await waitFor(() =>
      expect(result.current.watchlist).toEqual(["SH:CAT:1", "SH:CAT:2"])
    );
    expect(fetchMock).toHaveBeenCalledWith("/api/watchlist", {
      cache: "no-store",
    });
  });

  it("optimistically adds an id and POSTs it to the server", async () => {
    // GET (seed) → empty; POST → ok.
    fetchMock
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValue(jsonResponse(["SH:CAT:9"]));

    const { result } = renderView();
    await waitFor(() => expect(result.current.watchlist).toEqual([]));

    act(() => result.current.toggleWatch("SH:CAT:9"));
    // Optimistic: state updates synchronously.
    expect(result.current.watchlist).toEqual(["SH:CAT:9"]);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/watchlist",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ object_id: "SH:CAT:9" }),
        })
      )
    );
    // Still present after the POST resolves (no revert on success).
    expect(result.current.watchlist).toEqual(["SH:CAT:9"]);
  });

  it("optimistically removes an id and DELETEs it on the server", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(["SH:CAT:5"])) // seed
      .mockResolvedValue(jsonResponse([])); // DELETE

    const { result } = renderView();
    await waitFor(() => expect(result.current.watchlist).toEqual(["SH:CAT:5"]));

    act(() => result.current.toggleWatch("SH:CAT:5"));
    expect(result.current.watchlist).toEqual([]);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/watchlist/SH%3ACAT%3A5",
        expect.objectContaining({ method: "DELETE" })
      )
    );
    expect(result.current.watchlist).toEqual([]);
  });

  it("reverts the optimistic add when the POST fails", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse([])) // seed empty
      .mockResolvedValue(jsonResponse({ error: "no" }, 502)); // POST fails

    const { result } = renderView();
    await waitFor(() => expect(result.current.watchlist).toEqual([]));

    act(() => result.current.toggleWatch("SH:CAT:7"));
    expect(result.current.watchlist).toEqual(["SH:CAT:7"]); // optimistic

    // The failed POST reverts it back out.
    await waitFor(() => expect(result.current.watchlist).toEqual([]));
  });

  it("reverts the optimistic remove when the DELETE fails", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(["SH:CAT:3"])) // seed
      .mockResolvedValue(jsonResponse({ error: "no" }, 502)); // DELETE fails

    const { result } = renderView();
    await waitFor(() => expect(result.current.watchlist).toEqual(["SH:CAT:3"]));

    act(() => result.current.removeManyFromWatch(["SH:CAT:3"]));
    expect(result.current.watchlist).toEqual([]); // optimistic

    await waitFor(() =>
      expect(result.current.watchlist).toEqual(["SH:CAT:3"])
    );
  });

  it("migrates a legacy localStorage watchlist when the server is empty", async () => {
    window.localStorage.setItem(
      "spacehawk.watchlist",
      JSON.stringify(["SH:CAT:legacy"])
    );
    // GET (seed) → empty; the migration POST → ok.
    fetchMock
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValue(jsonResponse(["SH:CAT:legacy"]));

    const { result } = renderView();
    await waitFor(() =>
      expect(result.current.watchlist).toEqual(["SH:CAT:legacy"])
    );

    // The legacy id was pushed up to the server.
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/watchlist",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ object_id: "SH:CAT:legacy" }),
        })
      )
    );
  });

  it("prefers the server list over localStorage (no migration when server non-empty)", async () => {
    window.localStorage.setItem(
      "spacehawk.watchlist",
      JSON.stringify(["SH:CAT:old"])
    );
    fetchMock.mockResolvedValue(jsonResponse(["SH:CAT:server"]));

    const { result } = renderView();
    await waitFor(() =>
      expect(result.current.watchlist).toEqual(["SH:CAT:server"])
    );
    // No POST migration fired (only the seed GET).
    const posts = fetchMock.mock.calls.filter(
      (c) => (c[1] as RequestInit | undefined)?.method === "POST"
    );
    expect(posts).toHaveLength(0);
  });
});
