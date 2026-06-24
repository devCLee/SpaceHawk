// Flow coverage for the report chat panel (T9): recognized intent -> POST ->
// poll -> DONE -> download link; FAILED -> error + retry; double-submit guard;
// unrecognized intent -> help reply. fetch is mocked per test (no live engine).

import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ReportChatPanel from "../ReportChatPanel";
import {
  GlobeControlsProvider,
  useGlobeControls,
} from "../../context/GlobeControlsContext";
import { DebrisLayerProvider } from "../../context/DebrisLayerContext";
import { t } from "@/lib/i18n/t";

// useGlobeControls is mocked so the panel's per-country globe capture is
// deterministic + instant here. The real captureAllCountryGlobes now waits
// (bounded) for a Cesium viewer to register — that wait is unit-tested in
// GlobeControlsContext.capture.test.tsx; replaying it in every panel flow test
// would just add seconds. The real GlobeControlsProvider stays in the tree.
vi.mock("../../context/GlobeControlsContext", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../context/GlobeControlsContext")>();
  return { ...actual, useGlobeControls: vi.fn() };
});

// --- programmable fetch mock keyed on URL + method ---
type Json = Record<string, unknown>;
let postCalls: number;
let postBodies: Json[]; // each POST /api/reports body, in order
let statusResponses: Json[]; // consumed in order on each GET /api/reports/{id}
let postResponse: Json;

function jsonResponse(body: Json, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installFetch() {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    if (url === "/api/reports" && method === "POST") {
      postCalls += 1;
      postBodies.push(
        init?.body ? (JSON.parse(init.body as string) as Json) : {}
      );
      return jsonResponse(postResponse, 202);
    }
    if (url.startsWith("/api/reports/") && method === "GET") {
      const next = statusResponses.shift() ?? statusResponses[0];
      return jsonResponse(next);
    }
    return new Response(null, { status: 404 });
  }) as unknown as typeof fetch;
}

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <GlobeControlsProvider>
        <DebrisLayerProvider>
          <ReportChatPanel />
        </DebrisLayerProvider>
      </GlobeControlsProvider>
    </QueryClientProvider>
  );
}

function openPanel() {
  // The bottom-right launcher FAB carries the report title as its accessible
  // name; clicking it opens the chat card.
  fireEvent.click(screen.getByRole("button", { name: t("report.title") }));
}

function typeAndSend(text: string) {
  fireEvent.change(screen.getByPlaceholderText(t("report.placeholder")), {
    target: { value: text },
  });
  fireEvent.click(screen.getByText(t("report.send")));
}

beforeEach(() => {
  postCalls = 0;
  postBodies = [];
  postResponse = { job_id: "job-1", status: "PENDING" };
  statusResponses = [];
  installFetch();
  // Default: nothing capturable (no globe). Individual tests override.
  vi.mocked(useGlobeControls).mockReturnValue({
    captureAllCountryGlobes: async () => ({}),
  } as unknown as ReturnType<typeof useGlobeControls>);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ReportChatPanel", () => {
  it("recognized intent -> POST -> DONE -> download link", async () => {
    statusResponses = [{ job_id: "job-1", status: "DONE", download_url: "/x" }];
    renderPanel();
    openPanel();

    typeAndSend("generate daily report for 2026-01-07");

    const link = await screen.findByText(t("report.download"));
    expect(link).toHaveAttribute(
      "href",
      "/api/reports/job-1/download"
    );
    expect(postCalls).toBe(1);
  });

  it("omits the images field when no globe/heatmap is capturable", async () => {
    // No Cesium viewer and no heatmap canvas are registered in the test env, so
    // the panel captures nothing and the POST body carries no `images`.
    statusResponses = [{ job_id: "job-1", status: "DONE", download_url: "/x" }];
    renderPanel();
    openPanel();

    typeAndSend("generate daily report for 2026-01-07");

    await screen.findByText(t("report.download"));
    expect(postBodies).toHaveLength(1);
    expect(postBodies[0]).not.toHaveProperty("images");
    // Sanity: the request still carries the parsed intent.
    expect(postBodies[0]).toMatchObject({
      report_type: "daily",
      report_date: "2026-01-07",
    });
  });

  it("includes the four per-country globes in the POST body when capture yields them", async () => {
    // Stub useGlobeControls.captureAllCountryGlobes so the panel has the four
    // per-country snapshots, exercising the images-included branch without a live
    // Cesium viewer.
    const globes = { NK: "bms=", CN: "Y24=", RU: "cnU=", JP: "anA=" };
    vi.mocked(useGlobeControls).mockReturnValue({
      captureAllCountryGlobes: async () => globes,
    } as unknown as ReturnType<typeof useGlobeControls>);

    statusResponses = [{ job_id: "job-1", status: "DONE", download_url: "/x" }];
    renderPanel();
    openPanel();

    typeAndSend("generate daily report for 2026-01-07");

    await screen.findByText(t("report.download"));
    expect(postBodies).toHaveLength(1);
    expect(postBodies[0]).toMatchObject({
      images: { country_globes: globes },
    });
  });

  it("still POSTs (no images) when per-country capture fails", async () => {
    // captureAllCountryGlobes rejects -> the panel swallows it and submits an
    // image-less report (best-effort capture must never block the request).
    vi.mocked(useGlobeControls).mockReturnValue({
      captureAllCountryGlobes: async () => {
        throw new Error("viewer not ready");
      },
    } as unknown as ReturnType<typeof useGlobeControls>);

    statusResponses = [{ job_id: "job-1", status: "DONE", download_url: "/x" }];
    renderPanel();
    openPanel();

    typeAndSend("generate daily report for 2026-01-07");

    await screen.findByText(t("report.download"));
    expect(postBodies).toHaveLength(1);
    expect(postBodies[0]).not.toHaveProperty("images");
  });

  it("warns when the globe wasn't capturable (globes skipped notice)", async () => {
    // Default mock returns no globes -> the panel must surface the skip notice so
    // a globe-less report is never a silent surprise.
    statusResponses = [{ job_id: "job-1", status: "DONE", download_url: "/x" }];
    renderPanel();
    openPanel();

    typeAndSend("generate daily report for 2026-01-07");

    expect(
      await screen.findByText(t("report.globesSkipped"))
    ).toBeInTheDocument();
    expect(postBodies[0]).not.toHaveProperty("images");
  });

  it("FAILED status shows the reason and a retry button", async () => {
    statusResponses = [
      { job_id: "job-1", status: "FAILED", error_reason: "데이터 없음" },
    ];
    renderPanel();
    openPanel();

    typeAndSend("일일 보고서 생성");

    expect(
      await screen.findByText(t("report.failed", { reason: "데이터 없음" }))
    ).toBeInTheDocument();
    expect(screen.getByText(t("report.retry"))).toBeInTheDocument();
  });

  it("unrecognized intent shows a help reply and does not POST", async () => {
    renderPanel();
    openPanel();

    typeAndSend("what's the weather");

    expect(await screen.findByText(t("report.unrecognized"))).toBeInTheDocument();
    expect(postCalls).toBe(0);
  });

  it("guards against double-submit while a job is in flight", async () => {
    // Keep the job non-terminal so the input stays disabled.
    statusResponses = [{ job_id: "job-1", status: "RUNNING" }];
    renderPanel();
    openPanel();

    typeAndSend("daily report 2026-01-07");

    // Once the job is queued, the send button is disabled -> a second click
    // cannot fire another POST.
    await waitFor(() =>
      expect(screen.getByText(t("report.send"))).toBeDisabled()
    );
    fireEvent.click(screen.getByText(t("report.send")));
    expect(postCalls).toBe(1);
  });
});
