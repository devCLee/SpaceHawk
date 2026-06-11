"use client";

// Session state for the whole app. Validates the session against the engine via
// /api/auth/me (the reference GET_MY pattern, retry: 0) and exposes the subject
// the guards and Header read. The engine remains authoritative — this only
// shapes the UI; it never decides access on its own.

import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApiQuery } from "@/lib/api/useApiQuery";
import {
  isAdmin as roleIsAdmin,
  isAnalyst as roleIsAnalyst,
  type SessionUser,
} from "@/lib/auth";

export const AUTH_ME_KEY = ["auth", "me"];

interface AuthContextValue {
  user: SessionUser | null;
  isLoading: boolean;
  isError: boolean;
  isAdmin: boolean;
  isAnalyst: boolean;
  /** Re-validate the session (after sign-in / sign-out). */
  refresh: () => void;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useApiQuery<SessionUser>({
    queryKey: AUTH_ME_KEY,
    // retry:0 — a 401 is a definitive "no session", not a transient error.
    // staleTime 5m — the session rarely changes mid-visit and login/logout call
    // refresh() (invalidate) explicitly, so there's no need to re-validate on
    // every mount/navigation. (staleTime:0 refetched /api/auth/me constantly.)
    url: "/api/auth/me",
    options: { retry: 0, staleTime: 5 * 60_000 },
  });

  // A 401 surfaces as isError; treat anything but a clean hit as "no session".
  const user = isError ? null : data ?? null;

  const value = React.useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      isError,
      isAdmin: roleIsAdmin(user),
      isAnalyst: roleIsAnalyst(user),
      refresh: () => queryClient.invalidateQueries({ queryKey: AUTH_ME_KEY }),
    }),
    [user, isLoading, isError, queryClient]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
