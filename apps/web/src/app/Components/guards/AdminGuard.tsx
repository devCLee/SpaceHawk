"use client";

// AdminGuard — admin-only access control (the reference AdminGuard). Non-admins
// get an opaque empty page ("ask an administrator") rather than the content. The
// engine still enforces ADMIN + the IP allowlist on the data itself; this only
// hides the UI. Nest inside AuthGuard so the session is already resolved.

import { useAuth } from "@/app/context/AuthContext";
import Spinner from "@/app/Components/ui/Spinner";
import EmptyState from "@/app/Components/ui/EmptyState";

export default function AdminGuard({ children }: { children: React.ReactNode }) {
  const { isAdmin, isLoading } = useAuth();

  if (isLoading) return <Spinner />;
  if (!isAdmin) {
    return (
      <EmptyState
        title="404 — Not Found"
        message="You don't have access to this page. Ask an administrator if you need it."
      />
    );
  }
  return <>{children}</>;
}
