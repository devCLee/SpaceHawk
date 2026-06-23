"use client";

// Report job hooks for the chat panel (T9): a mutation that queues an HWPX job
// and a query that polls its status until DONE/FAILED. Mirrors the house
// useApiQuery / queryKeys convention; the BFF routes (/api/reports*) own the
// engine auth.

import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { useApiQuery, type ApiQueryOptions } from "@/lib/api/useApiQuery";
import { queryKeys } from "@/lib/api/queryKeys";
import { http } from "@/lib/api/apiClient";
import type { ReportJob, ReportRequest } from "@/lib/orbital-engine";

/** Poll interval while a job is PENDING/RUNNING. */
const POLL_MS = 2000;

/** Queue (or idempotently re-attach to) a report job via POST /api/reports. */
export function useCreateReport(): UseMutationResult<
  ReportJob,
  Error,
  ReportRequest
> {
  return useMutation<ReportJob, Error, ReportRequest>({
    mutationFn: (body) => http.post<ReportJob>("/api/reports", body),
  });
}

/** Poll one report job until it reaches a terminal status. Disabled when jobId
 *  is null; stops refetching once status is DONE or FAILED. */
export function useReportJob(jobId: string | null) {
  const options: ApiQueryOptions<ReportJob> = {
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "DONE" || status === "FAILED" ? false : POLL_MS;
    },
  };
  return useApiQuery<ReportJob>({
    queryKey: queryKeys.reportJob(jobId ?? "none"),
    url: `/api/reports/${encodeURIComponent(jobId ?? "none")}`,
    options,
  });
}
