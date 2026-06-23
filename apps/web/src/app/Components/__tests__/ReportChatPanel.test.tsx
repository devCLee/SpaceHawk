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
import { t } from "@/lib/i18n/t";

// --- programmable fetch mock keyed on URL + method ---
type Json = Record<string, unknown>;
let postCalls: number;
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
      <ReportChatPanel />
    </QueryClientProvider>
  );
}

function openPanel() {
  fireEvent.click(screen.getByText(t("report.title")));
}

function typeAndSend(text: string) {
  fireEvent.change(screen.getByPlaceholderText(t("report.placeholder")), {
    target: { value: text },
  });
  fireEvent.click(screen.getByText(t("report.send")));
}

beforeEach(() => {
  postCalls = 0;
  postResponse = { job_id: "job-1", status: "PENDING" };
  statusResponses = [];
  installFetch();
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
