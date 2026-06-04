"use client";

// GuestGuard — the inverse of AuthGuard (the reference GuestGuard). Keeps an
// already-authenticated user off guest-only pages (e.g. /signin) by bouncing
// them home.

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/app/context/AuthContext";
import Spinner from "@/app/Components/ui/Spinner";

export default function GuestGuard({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && user) {
      router.replace("/");
    }
  }, [isLoading, user, router]);

  if (isLoading) return <Spinner />;
  if (user) return null; // redirecting
  return <>{children}</>;
}
