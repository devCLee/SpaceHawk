"use client";

// Top bar. Shows the signed-in operator (username · role) and a sign-out action;
// admins get a link to the audit log. Reads the session from AuthContext.

import { useRouter } from "next/navigation";
import { useAuth } from "@/app/context/AuthContext";
import { http } from "@/lib/api/apiClient";

export default function Header() {
  const { user, isAdmin, refresh } = useAuth();
  const router = useRouter();

  async function signOut() {
    try {
      await http.post("/api/auth/logout");
    } finally {
      refresh();
      router.replace("/signin");
    }
  }

  return (
    <header className="fixed top-0 inset-x-0 z-50 h-14 px-10 flex items-center justify-between bg-black/70 backdrop-blur-md">
      <div className="text-sm font-semibold tracking-wide">SpaceHawk</div>
      <nav className="flex items-center gap-6 text-sm">
        <a href="#menu-item-1" className="hover:text-slate-200 transition-colors">
          Live
        </a>
        <a href="#menu-item-2" className="hover:text-slate-200 transition-colors">
          Sandbox
        </a>
        {user && (
          <>
            {isAdmin && (
              <a href="/admin/audit" className="hover:text-slate-200 transition-colors">
                Audit
              </a>
            )}
            <span className="text-slate-400">
              {user.username} · {user.role}
            </span>
            <button
              onClick={signOut}
              className="rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300 transition-colors hover:bg-slate-800"
            >
              Sign out
            </button>
          </>
        )}
      </nav>
    </header>
  );
}
