// Pure, unit-testable intent parser for the report chat panel (T9, PR1).
//
// PR1 scope: this is NOT a conversational LLM. It recognizes a single intent —
// "generate a daily report" — in English or Korean, extracts an explicit date if
// one is present (else defaults to today), and returns null for anything it does
// not understand so the panel can show a help message. No engine call, no I/O.

export interface ReportIntent {
  reportType: "daily";
  /** YYYY-MM-DD (local date). */
  reportDate: string;
}

/** Today's date as YYYY-MM-DD in the local timezone (no UTC drift). */
export function todayISO(now: Date = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

// "daily report" (EN, allows "daily ... report") or 일일/일간 ... 보고(서) (KO).
const DAILY_INTENT =
  /(daily\s+(?:\w+\s+)*report)|((?:일일|일간)\s*\S*\s*보고서?)/i;

// Explicit dates: ISO 2026-01-07, 2026.01.07, 2026/01/07, or KO 2026년 1월 7일.
const ISO_DATE = /\b(\d{4})[-./](\d{1,2})[-./](\d{1,2})\b/;
const KO_DATE = /(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일/;

function toISO(y: string, mo: string, d: string): string | null {
  const year = Number(y);
  const month = Number(mo);
  const day = Number(d);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** Extract an explicit report date from free text, or null if none is present. */
function extractDate(message: string): string | null {
  const iso = ISO_DATE.exec(message);
  if (iso) return toISO(iso[1], iso[2], iso[3]);
  const ko = KO_DATE.exec(message);
  if (ko) return toISO(ko[1], ko[2], ko[3]);
  return null;
}

/**
 * Parse a chat message into a report intent, or null if unrecognized.
 *
 * - Recognizes "daily report" / "일일 보고(서)" / "일간 보고".
 * - Uses an explicit date when present; otherwise defaults to today.
 */
export function parseReportIntent(
  message: string,
  now: Date = new Date()
): ReportIntent | null {
  if (!DAILY_INTENT.test(message)) return null;
  const reportDate = extractDate(message) ?? todayISO(now);
  return { reportType: "daily", reportDate };
}
