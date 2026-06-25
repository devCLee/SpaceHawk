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
// Surface: a bottom-right floating launcher (FAB) toggles the chat card open and
// closed. Mounted at the dashboard page level (not the left rail) so it stays
// pinned to the corner regardless of the analyst rail's open/closed state.
//
// PR1 is intent parsing, NOT a conversational LLM (see reportIntent.ts).

import React from "react";
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
  // Launcher open/closed — the FAB toggles the chat card.
  const [open, setOpen] = React.useState(false);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  // The job currently being generated, plus the date that produced it (for the
  // ready/download copy). Cleared on retry so a fresh request can be issued.
  const [activeJob, setActiveJob] = React.useState<{
    id: string;
    date: string;
  } | null>(null);
  // The last intent we tried, kept so "retry" can re-fire it without retyping.
  const [lastRequest, setLastRequest] = React.useState<ReportRequest | null>(
    null
  );

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
      // Tell the user when the globe wasn't capturable (e.g. submitted before the
      // 3D globe finished mounting) so a globe-less report is never a silent
      // surprise — they can regenerate with the globe on screen.
      const capturedGlobes = images?.country_globes;
      if (!capturedGlobes || Object.keys(capturedGlobes).length === 0) {
        pushBot(t("report.globesSkipped"));
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
    setMessages((prev) => [...prev, { id: nextMsgId++, role: "user", text }]);
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

  // Reset the chat record: drop all messages, the active/last job, and any
  // half-typed input. The launcher stays open so the analyst can start fresh.
  const handleReset = React.useCallback(() => {
    setMessages([]);
    setActiveJob(null);
    setLastRequest(null);
    setInput("");
  }, []);

  return (
    <div className="report-chat">
      <style>{REPORT_CHAT_CSS}</style>

      {open && (
        <div
          className="report-chat-card"
          role="dialog"
          aria-label={t("report.title")}
        >
          <div className="report-chat-head">
            <span style={s.panelTitle}>{t("report.title")}</span>
            <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
              <button
                type="button"
                className="report-chat-close"
                onClick={handleReset}
                aria-label={t("report.reset")}
                title={t("report.reset")}
              >
                <RotateCcwIcon />
              </button>
              <button
                type="button"
                className="report-chat-close"
                onClick={() => setOpen(false)}
                aria-label={t("common.cancel")}
              >
                <CloseIcon />
              </button>
            </div>
          </div>

          <div className="report-chat-body">
            <p style={{ ...s.muted, fontSize: 11, margin: 0 }}>
              {t("report.intro")}
            </p>

            {messages.length > 0 && (
              <ul
                style={{
                  ...s.list,
                  maxHeight: 200,
                  gap: 6,
                  display: "flex",
                  flexDirection: "column",
                }}
              >
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
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                  position: "relative",
                }}
              >
                <button
                  type="button"
                  className="report-chat-close"
                  onClick={() => setActiveJob(null)}
                  aria-label={t("common.cancel")}
                  style={{ position: "absolute", top: 0, right: 0 }}
                >
                  <CloseIcon />
                </button>
                <span style={{ fontSize: 12, paddingRight: 20 }}>
                  {t("report.ready", { date: activeJob.date })}
                </span>
                <a
                  href={`/api/reports/${encodeURIComponent(
                    activeJob.id
                  )}/download`}
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
                className="break-keep"
              >
                {t("report.send")}
              </button>
            </div>
          </div>
        </div>
      )}

      <button
        type="button"
        className="report-fab"
        onClick={() => setOpen((o) => !o)}
        title={t("report.title")}
        aria-label={t("report.title")}
        aria-expanded={open}
      >
        <MessageSquareMoreIcon />
      </button>
    </div>
  );
};

// lucide `message-square-more` — the report-chat launcher icon.
function MessageSquareMoreIcon() {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <path d="M8 10h.01" />
      <path d="M12 10h.01" />
      <path d="M16 10h.01" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    >
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

// lucide `rotate-ccw` — the reset-chat control icon.
function RotateCcwIcon() {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5" />
    </svg>
  );
}

// Scoped to `.report-chat`. Tokens match the dark operational theme (panel
// rgba(8,12,20), sky accent) used by the Header toolbar and control panels.
const REPORT_CHAT_CSS = `
/* bottom:56px clears Cesium's timeline strip along the viewer's bottom edge
   so the launcher never overlaps the playback control. */
.report-chat{position:fixed;right:24px;bottom:56px;z-index:40;
  display:flex;flex-direction:column;align-items:flex-end;gap:12px;
  font-family:system-ui,sans-serif}
.report-fab{width:54px;height:54px;border-radius:50%;border:0;cursor:pointer;
  display:grid;place-items:center;color:#04222e;align-self:flex-end;
  background:linear-gradient(180deg,#38bdf8,#0ea5e9);
  box-shadow:0 8px 24px rgba(14,165,233,.4),0 1px 0 rgba(255,255,255,.3) inset;
  transition:transform .15s,box-shadow .15s}
.report-fab:hover{transform:translateY(-1px);box-shadow:0 10px 28px rgba(14,165,233,.5)}
.report-fab .icon{width:24px;height:24px;display:block}
.report-chat-card{width:330px;max-height:calc(100vh - 140px);
  display:flex;flex-direction:column;color:#e6edf3;
  background:rgba(8,12,20,0.96);border:1px solid rgba(255,255,255,0.12);
  border-radius:10px;box-shadow:0 20px 50px rgba(0,0,0,.6);overflow:hidden}
.report-chat-head{display:flex;align-items:center;justify-content:space-between;
  padding:10px 12px;border-bottom:1px solid rgba(255,255,255,0.08)}
.report-chat-close{appearance:none;border:0;background:transparent;color:#7d8da0;
  cursor:pointer;width:24px;height:24px;display:grid;place-items:center;border-radius:5px;
  transition:background .12s,color .12s}
.report-chat-close:hover{background:rgba(255,255,255,0.08);color:#e6edf3}
.report-chat-close .icon{width:15px;height:15px;display:block}
.report-chat-body{padding:10px 12px;display:flex;flex-direction:column;gap:8px;overflow-y:auto}
`;

export default ReportChatPanel;
