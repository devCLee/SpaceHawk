"use client";

// Intent-driven report chat panel (T9, PR1). The user types a request like
// "2026-01-07 일일 보고서 생성"; parseReportIntent() turns it into a {daily, date}
// intent (defaulting to today). On a recognized intent the panel POSTs to the
// engine (via the BFF) to queue an idempotent HWPX job, then polls the job status
// until DONE (download link) or FAILED (error + retry). Unrecognized input gets a
// help reply. Double-submit is guarded (input disabled while a job is in flight;
// the engine's idempotency is the backstop). The engine enforces ANALYST
// clearance — a 401/403 surfaces as a request-failed reply.
//
// PR1 is intent parsing, NOT a conversational LLM (see reportIntent.ts).

import React from "react";
import CollapsiblePanel from "./CollapsiblePanel";
import * as s from "./panelStyles";
import { t } from "@/lib/i18n/t";
import { parseReportIntent } from "@/lib/reportIntent";
import { useCreateReport, useReportJob } from "@/lib/api/useReports";
import type { ReportImagesRequest, ReportRequest } from "@/lib/orbital-engine";
import { useGlobeControls } from "../context/GlobeControlsContext";
import { useDebrisLayer } from "../context/DebrisLayerContext";

interface ChatMessage {
  id: number;
  role: "user" | "bot";
  text: string;
}

let nextMsgId = 0;

export const ReportChatPanel: React.FunctionComponent = () => {
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  // The job currently being generated, plus the date that produced it (for the
  // ready/download copy). Cleared on retry so a fresh request can be issued.
  const [activeJob, setActiveJob] = React.useState<{
    id: string;
    date: string;
  } | null>(null);
  // The last intent we tried, kept so "retry" can re-fire it without retyping.
  const [lastRequest, setLastRequest] = React.useState<ReportRequest | null>(null);

  // True while the per-country globe snapshots are being captured (before the
  // POST fires). Folded into `inFlight` so the submit control is disabled across
  // the whole capture -> post -> poll cycle (no double-submit).
  const [isCapturing, setIsCapturing] = React.useState(false);

  const createReport = useCreateReport();
  const { data: job } = useReportJob(activeJob?.id ?? null);
  const { captureAllCountryGlobes } = useGlobeControls();
  const { captureHeatmap } = useDebrisLayer();

  // Best-effort report images (R8): snapshot the four per-country globe views
  // (NK/CN/RU/JP) by driving the camera over each country in turn, plus the 2D
  // heatmap if its overlay is open. Async because the globe streams tiles between
  // camera moves. Returns undefined when nothing is capturable, so the POST omits
  // images and still yields a valid report. Never throws — capture failures yield
  // a partial/empty result.
  const captureImages = React.useCallback(async (): Promise<
    ReportImagesRequest | undefined
  > => {
    const images: ReportImagesRequest = {};
    try {
      const globes = await captureAllCountryGlobes();
      if (Object.keys(globes).length > 0) images.country_globes = globes;
    } catch {
      /* capture is best-effort — submit proceeds without the globes */
    }
    const heatmap = captureHeatmap();
    if (heatmap) images.debris_heatmap = heatmap;
    return Object.keys(images).length > 0 ? images : undefined;
  }, [captureAllCountryGlobes, captureHeatmap]);

  const pushBot = React.useCallback((text: string) => {
    setMessages((prev) => [...prev, { id: nextMsgId++, role: "bot", text }]);
  }, []);

  // In-flight = capturing snapshots, a queued job not yet terminal, or the POST
  // mutation pending. Capturing is part of the cycle so the control stays disabled
  // from the first click through the whole capture -> post -> poll flow.
  const status = job?.status;
  const polling =
    activeJob !== null && status !== "DONE" && status !== "FAILED";
  const inFlight = isCapturing || createReport.isPending || polling;

  const submit = React.useCallback(
    async (request: ReportRequest) => {
      setLastRequest(request);
      pushBot(t("report.queued", { date: request.report_date }));
      // Capture fresh at submit time so the snapshots reflect the live view.
      setIsCapturing(true);
      let images: ReportImagesRequest | undefined;
      try {
        images = await captureImages();
      } finally {
        setIsCapturing(false);
      }
      const withImages: ReportRequest = { ...request, images };
      createReport.mutate(withImages, {
        onSuccess: (created) => {
          setActiveJob({ id: created.job_id, date: request.report_date });
        },
        onError: () => {
          pushBot(t("report.requestFailed"));
        },
      });
    },
    [createReport, pushBot, captureImages]
  );

  const handleSend = React.useCallback(() => {
    const text = input.trim();
    if (text === "" || inFlight) return;
    setMessages((prev) => [
      ...prev,
      { id: nextMsgId++, role: "user", text },
    ]);
    setInput("");
    const intent = parseReportIntent(text);
    if (intent === null) {
      pushBot(t("report.unrecognized"));
      return;
    }
    void submit({
      report_type: intent.reportType,
      report_date: intent.reportDate,
    });
  }, [input, inFlight, pushBot, submit]);

  const handleRetry = React.useCallback(() => {
    if (lastRequest === null) return;
    setActiveJob(null);
    void submit(lastRequest);
  }, [lastRequest, submit]);

  return (
    <CollapsiblePanel title={t("report.title")}>
      <p style={{ ...s.muted, fontSize: 11, margin: 0 }}>{t("report.intro")}</p>

      {messages.length > 0 && (
        <ul style={{ ...s.list, maxHeight: 200, gap: 6, display: "flex", flexDirection: "column" }}>
          {messages.map((m) => (
            <li
              key={m.id}
              style={{
                listStyle: "none",
                display: "flex",
                flexDirection: "column",
                gap: 1,
                alignItems: m.role === "user" ? "flex-end" : "flex-start",
              }}
            >
              <span style={{ ...s.muted, fontSize: 10 }}>
                {m.role === "user" ? t("report.you") : t("report.bot")}
              </span>
              <span
                style={{
                  fontSize: 12,
                  padding: "4px 8px",
                  borderRadius: 4,
                  maxWidth: "85%",
                  background:
                    m.role === "user"
                      ? "rgba(90,176,255,0.16)"
                      : "rgba(255,255,255,0.06)",
                }}
              >
                {m.text}
              </span>
            </li>
          ))}
        </ul>
      )}

      {/* Live job state for the active request. */}
      {activeJob && (status === "PENDING" || status === undefined) && (
        <p style={{ ...s.muted, fontSize: 12, margin: 0 }} role="status">
          {t("report.pending")}
        </p>
      )}
      {activeJob && status === "RUNNING" && (
        <p style={{ ...s.muted, fontSize: 12, margin: 0 }} role="status">
          {t("report.running")}
        </p>
      )}
      {activeJob && status === "DONE" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12 }}>
            {t("report.ready", { date: activeJob.date })}
          </span>
          <a
            href={`/api/reports/${encodeURIComponent(activeJob.id)}/download`}
            style={{
              ...s.input,
              width: "auto",
              textAlign: "center",
              textDecoration: "none",
              color: "#5ab0ff",
              cursor: "pointer",
            }}
          >
            {t("report.download")}
          </a>
        </div>
      )}
      {activeJob && status === "FAILED" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={s.error}>
            {t("report.failed", {
              reason: job?.error_reason ?? t("report.failed.noReason"),
            })}
          </span>
          <button
            type="button"
            onClick={handleRetry}
            style={{ ...s.input, width: "auto", cursor: "pointer" }}
          >
            {t("report.retry")}
          </button>
        </div>
      )}

      <div style={{ display: "flex", gap: 6 }}>
        <input
          style={s.input}
          value={input}
          placeholder={t("report.placeholder")}
          disabled={inFlight}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSend();
          }}
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={inFlight || input.trim() === ""}
          style={{
            ...s.input,
            width: "auto",
            cursor: inFlight ? "default" : "pointer",
            opacity: inFlight ? 0.5 : 1,
          }}
        >
          {t("report.send")}
        </button>
      </div>
    </CollapsiblePanel>
  );
};

export default ReportChatPanel;
