"use client";

// Typed contract between the Audit Log table and the data-fetching layer.
//
// The engine paginates and filters server-side (see orbital_engine/api/audit.py):
// `AuditQuery` is what the table asks for, `AuditPage` is what the server returns.
// `buildAuditParams` is the single place the query is mapped to wire params, so the
// table never hand-builds query strings and the param names stay in one spot.

import { useApiQuery } from "./useApiQuery";
import type { QueryParams } from "./apiClient";

/** One audit row, mirroring the engine's `AuditEntry` model. */
export interface AuditEntry {
  id: number;
  ts: string;
  subject: string | null;
  role: string | null;
  service: string | null;
  source_ip: string | null;
  domain: string;
  action: string;
  decision: string;
  code: string;
  reason: string;
  method: string | null;
  path: string | null;
}

/** A page of rows plus the total matching count (drives page-count math). */
export interface AuditPage {
  rows: AuditEntry[];
  total: number;
}

/**
 * Everything the server needs to answer one table render: the pagination window
 * plus the active filters. Substring filters (`subject`, `path`) are contains
 * matches; the array filters are inclusive-OR multi-selects. Omitted/empty fields
 * mean "no filter".
 */
export interface AuditQuery {
  pageIndex: number;
  pageSize: number;
  subject?: string;
  path?: string;
  source_ip?: string;
  decision?: string[];
  role?: string[];
  domain?: string[];
  action?: string[];
  /** Inclusive timestamp range bounds, ISO 8601 strings. */
  tsFrom?: string;
  tsTo?: string;
}

/** Map a typed query to wire params (offset = page * size; arrays repeat). */
export function buildAuditParams(query: AuditQuery): QueryParams {
  return {
    limit: query.pageSize,
    offset: query.pageIndex * query.pageSize,
    subject: query.subject,
    path: query.path,
    source_ip: query.source_ip,
    decision: query.decision,
    role: query.role,
    domain: query.domain,
    action: query.action,
    ts_from: query.tsFrom,
    ts_to: query.tsTo,
  };
}

/**
 * Fetch one page of the audit log. `keepPreviousData` keeps the prior page visible
 * while the next request is in flight, so paging/filtering shows a loading hint
 * (via `isFetching`) instead of flashing empty. The full query is part of the key,
 * so any pagination or filter change refetches automatically.
 */
export function useAuditLog(query: AuditQuery) {
  return useApiQuery<AuditPage>({
    queryKey: ["audit", "log", query],
    url: "/api/audit",
    options: { params: buildAuditParams(query), keepPreviousData: true, retry: 0 },
  });
}
