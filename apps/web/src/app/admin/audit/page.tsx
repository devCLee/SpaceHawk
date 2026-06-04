"use client";

// Admin-only audit viewer (Stage 5). Reads the engine's immutable audit log via
// the BFF and lists recent access decisions. Double-guarded: AuthGuard ensures a
// session, AdminGuard ensures ADMIN; the engine enforces both again on the data.

import AuthGuard from "@/app/Components/guards/AuthGuard";
import AdminGuard from "@/app/Components/guards/AdminGuard";
import { useApiQuery } from "@/lib/api/useApiQuery";

interface AuditEntry {
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

function AuditTable() {
  const { data, isLoading, isError } = useApiQuery<AuditEntry[]>({
    queryKey: ["audit", "log"],
    url: "/api/audit",
    options: { params: { limit: 200 }, retry: 0 },
  });

  if (isLoading) return <p className="p-8 text-sm text-slate-400">Loading audit log…</p>;
  if (isError) return <p className="p-8 text-sm text-red-400">Failed to load the audit log.</p>;

  const rows = data ?? [];
  return (
    <main className="min-h-screen bg-black px-8 pt-20 pb-8 text-slate-200">
      <h1 className="mb-4 text-lg font-semibold">Audit Log</h1>
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              {["Time", "Subject", "Role", "Domain", "Action", "Decision", "Reason", "Source IP", "Path"].map(
                (h) => (
                  <th key={h} className="px-3 py-2 font-medium">
                    {h}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-slate-800/60">
                <td className="px-3 py-1.5 whitespace-nowrap text-slate-400">
                  {new Date(r.ts).toLocaleString()}
                </td>
                <td className="px-3 py-1.5">{r.subject ?? "—"}</td>
                <td className="px-3 py-1.5">{r.role ?? "—"}</td>
                <td className="px-3 py-1.5">{r.domain}</td>
                <td className="px-3 py-1.5">{r.action}</td>
                <td
                  className={`px-3 py-1.5 font-medium ${
                    r.decision === "deny" ? "text-red-400" : "text-emerald-400"
                  }`}
                >
                  {r.decision}
                </td>
                <td className="px-3 py-1.5 text-slate-400">{r.reason}</td>
                <td className="px-3 py-1.5 text-slate-400">{r.source_ip ?? "—"}</td>
                <td className="px-3 py-1.5 text-slate-400">{r.path ?? "—"}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-slate-500">
                  No audit entries yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}

export default function AuditPage() {
  return (
    <AuthGuard>
      <AdminGuard>
        <AuditTable />
      </AdminGuard>
    </AuthGuard>
  );
}
