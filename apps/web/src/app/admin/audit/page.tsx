"use client";

// Admin-only audit viewer (Stage 5). Reads the engine's immutable audit log via
// the BFF and lists access decisions. Double-guarded: AuthGuard ensures a session,
// AdminGuard ensures ADMIN; the engine enforces both again on the data. The table
// itself (pagination + filtering, all server-side) lives in AuditTable.

import AuthGuard from "@/app/Components/guards/AuthGuard";
import AdminGuard from "@/app/Components/guards/AdminGuard";
import AuditTable from "./AuditTable";

export default function AuditPage() {
  return (
    <AuthGuard>
      <AdminGuard>
        <AuditTable />
      </AdminGuard>
    </AuthGuard>
  );
}
