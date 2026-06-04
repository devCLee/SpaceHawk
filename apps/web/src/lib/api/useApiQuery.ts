"use client";

// useQuery wrapping hook (house convention — see team's useApiQuery.ts). Adapted
// to SpaceHawk's fetch-based same-origin `http` client and Error (no axios).

import {
  keepPreviousData as keepPreviousDataFn,
  useQuery,
  type QueryKey,
  type UseQueryOptions,
  type UseQueryResult,
} from "@tanstack/react-query";
import { http, type QueryParams } from "./apiClient";

export type ApiQueryOptions<TData> = Omit<
  UseQueryOptions<TData, Error, TData, QueryKey>,
  "queryKey" | "queryFn"
> & {
  /** GET query parameters (e.g. { q, limit }). */
  params?: QueryParams;
  keepPreviousData?: boolean;
};

interface UseApiQueryParams<TData> {
  queryKey: QueryKey;
  url: string;
  options?: ApiQueryOptions<TData>;
}

export function useApiQuery<TData>({
  queryKey,
  url,
  options,
}: UseApiQueryParams<TData>): UseQueryResult<TData, Error> {
  const { params, keepPreviousData, ...restOptions } = options ?? {};
  return useQuery<TData, Error, TData, QueryKey>({
    queryKey,
    queryFn: ({ signal }) => http.get<TData>(url, params, { signal }),
    placeholderData: keepPreviousData ? keepPreviousDataFn : undefined,
    ...restOptions,
  });
}
