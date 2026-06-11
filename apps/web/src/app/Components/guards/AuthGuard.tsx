"use client";

// AuthGuard — userStore-equivalent access control (the reference AuthGuard).
// Renders the protected subtree OPTIMISTICALLY so the heavy dashboard (Cesium +
// catalog) starts loading in parallel with the /api/auth/me round-trip instead
// of behind a blocking spinner. The moment the session resolves as invalid we
// stop rendering it and bounce to /signin. Safe because the engine authorizes
// every data call itself and the sensitive panels (alerts/audit/maneuvers) are
// server-gated — the only thing visible during the in-flight check is the
// globe's public TLE view.

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useAuth } from "@/app/context/AuthContext";
import { t } from "@/lib/i18n/t";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, isLoading, isError } = useAuth();
  const router = useRouter();

  const denied = !isLoading && (isError || !user);

  useEffect(() => {
    if (denied) {
      toast.warning(t("guard.signInRequired"));
      router.replace("/signin");
    }
  }, [denied, router]);

  // Don't block paint on the session check — render the subtree optimistically
  // so the globe loads in parallel, and only hide it once the session is known
  // invalid (the effect above then redirects to /signin).
  if (denied) return null;
  return <>{children}</>;
}
