// BFF watchlist proxy route tests (A2). The engine client is mocked — these
// assert the routes forward GET/POST/DELETE to the engine and map errors to a
// sensible same-origin response. No live engine, no real fetch.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/orbital-engine", () => ({
  getWatchlist: vi.fn(),
  addWatchlist: vi.fn(),
  removeWatchlist: vi.fn(),
}));

import { getWatchlist, addWatchlist, removeWatchlist } from "@/lib/orbital-engine";
import { GET, POST } from "../route";
import { DELETE } from "../[id]/route";

const mockGet = vi.mocked(getWatchlist);
const mockAdd = vi.mocked(addWatchlist);
const mockRemove = vi.mocked(removeWatchlist);

beforeEach(() => {
  vi.clearAllMocks();
});

function postReq(body: unknown): Request {
  return new Request("http://localhost/api/watchlist", {
    method: "POST",
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

describe("GET /api/watchlist", () => {
  it("forwards to the engine and returns the list", async () => {
    mockGet.mockResolvedValue(["SH:CAT:000025544", "SH:CAT:000043013"]);
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual([
      "SH:CAT:000025544",
      "SH:CAT:000043013",
    ]);
    expect(mockGet).toHaveBeenCalledTimes(1);
  });

  it("maps an engine failure to 502", async () => {
    mockGet.mockRejectedValue(new Error("orbital-engine /watchlist failed: 401"));
    const res = await GET();
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "orbital-engine unavailable" });
  });
});

describe("POST /api/watchlist", () => {
  it("forwards the object_id and returns the updated list", async () => {
    mockAdd.mockResolvedValue(["SH:CAT:000025544"]);
    const res = await POST(postReq({ object_id: "SH:CAT:000025544" }));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(["SH:CAT:000025544"]);
    expect(mockAdd).toHaveBeenCalledWith("SH:CAT:000025544");
  });

  it("rejects a missing object_id with 400", async () => {
    const res = await POST(postReq({}));
    expect(res.status).toBe(400);
    expect(mockAdd).not.toHaveBeenCalled();
  });

  it("rejects an invalid JSON body with 400", async () => {
    const res = await POST(postReq("not json"));
    expect(res.status).toBe(400);
    expect(mockAdd).not.toHaveBeenCalled();
  });

  it("maps an engine failure to 502", async () => {
    mockAdd.mockRejectedValue(new Error("boom"));
    const res = await POST(postReq({ object_id: "SH:CAT:000025544" }));
    expect(res.status).toBe(502);
  });
});

describe("DELETE /api/watchlist/[id]", () => {
  it("forwards the id and returns the updated list", async () => {
    mockRemove.mockResolvedValue([]);
    const res = await DELETE(
      new Request("http://localhost/api/watchlist/SH:CAT:000025544", {
        method: "DELETE",
      }),
      { params: Promise.resolve({ id: "SH:CAT:000025544" }) }
    );
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual([]);
    expect(mockRemove).toHaveBeenCalledWith("SH:CAT:000025544");
  });

  it("maps an engine failure to 502", async () => {
    mockRemove.mockRejectedValue(new Error("boom"));
    const res = await DELETE(
      new Request("http://localhost/api/watchlist/x", { method: "DELETE" }),
      { params: Promise.resolve({ id: "x" }) }
    );
    expect(res.status).toBe(502);
  });
});
