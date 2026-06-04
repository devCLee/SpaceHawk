// Client-side HTTP helper for the dashboard's same-origin BFF calls
// (browser -> Next /api/* -> private engine, dev-plan §4.1).
//
// Mirrors the team's apiClient/http + getErrorMessage convention, adapted to
// SpaceHawk: same-origin fetch instead of an axios instance pointed at the
// backend, and no auth/refresh interceptor yet (that lands with Stage 5). The
// `http` surface is intentionally the same shape so callers/useApiQuery match
// the house style.

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// A flat bag of GET query params. Typed as `object` so plain interfaces (e.g.
// CatalogQuery) are accepted without an index signature; values are stringified.
export type QueryParams = object;

function withParams(url: string, params?: QueryParams): string {
  if (!params) return url;
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      sp.set(key, String(value));
    }
  }
  const qs = sp.toString();
  return qs ? `${url}?${qs}` : url;
}

export const http = {
  get: async <T>(
    url: string,
    params?: QueryParams,
    init?: RequestInit
  ): Promise<T> => {
    const res = await fetch(withParams(url, params), {
      cache: "no-store",
      ...init,
    });
    if (!res.ok) {
      throw new ApiError(res.status, `GET ${url} failed: ${res.status}`);
    }
    return res.json() as Promise<T>;
  },
};

/** Parse an error into a user-facing message (house convention). */
export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 404:
        return "Not found.";
      case 502:
        return "Service unavailable.";
      default:
        return `Request failed (code: ${error.status}).`;
    }
  }
  if (error instanceof Error) return error.message;
  return "Unexpected error.";
}
