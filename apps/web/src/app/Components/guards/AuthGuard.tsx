"use client";

// AuthGuard — userStore-equivalent access control (the reference AuthGuard).
// While the session validates: spinner. On failure / no session: warn + bounce
// to /signin. On success: render the protected subtree.

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useAuth } from "@/app/context/AuthContext";
import Spinner from "@/app/Components/ui/Spinner";
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

  if (isLoading) return <Spinner />;
  if (denied) return null; // redirecting
  return <>{children}</>;
}
