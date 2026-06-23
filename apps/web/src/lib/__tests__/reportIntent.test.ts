import { describe, it, expect } from "vitest";
import { parseReportIntent, todayISO } from "@/lib/reportIntent";

// Fixed clock so the "default to today" branch is deterministic.
const NOW = new Date(2026, 0, 15, 9, 30); // 2026-01-15 local

describe("parseReportIntent", () => {
  it("recognizes an English daily report with an explicit ISO date", () => {
    expect(parseReportIntent("generate daily report for 2026-01-07", NOW)).toEqual({
      reportType: "daily",
      reportDate: "2026-01-07",
    });
  });

  it("recognizes Korean phrasing (일일 보고서) with a Korean date", () => {
    expect(parseReportIntent("2026년 1월 7일 일일 보고서 생성", NOW)).toEqual({
      reportType: "daily",
      reportDate: "2026-01-07",
    });
  });

  it("recognizes the 일간 보고 variant", () => {
    const result = parseReportIntent("일간 보고 만들어줘", NOW);
    expect(result).not.toBeNull();
    expect(result?.reportType).toBe("daily");
  });

  it("defaults to today when no date is given", () => {
    expect(parseReportIntent("daily report please", NOW)).toEqual({
      reportType: "daily",
      reportDate: "2026-01-15",
    });
  });

  it("accepts dotted and slashed ISO-style dates", () => {
    expect(parseReportIntent("daily report 2026.01.07", NOW)?.reportDate).toBe(
      "2026-01-07"
    );
    expect(parseReportIntent("daily report 2026/1/7", NOW)?.reportDate).toBe(
      "2026-01-07"
    );
  });

  it("rejects an out-of-range date as if absent (falls back to today)", () => {
    // 2026-13-40 is not a valid date -> treated as no explicit date.
    expect(parseReportIntent("daily report 2026-13-40", NOW)?.reportDate).toBe(
      "2026-01-15"
    );
  });

  it("returns null for unrecognized messages", () => {
    expect(parseReportIntent("what's the weather?", NOW)).toBeNull();
    expect(parseReportIntent("show me the catalog", NOW)).toBeNull();
    expect(parseReportIntent("", NOW)).toBeNull();
  });
});

describe("todayISO", () => {
  it("formats the local date as YYYY-MM-DD with zero padding", () => {
    expect(todayISO(new Date(2026, 2, 5))).toBe("2026-03-05");
  });
});
