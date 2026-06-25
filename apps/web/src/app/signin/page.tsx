"use client";

// Sign-in screen. Posts credentials to the same-origin /api/auth/login (which
// relays the engine-issued session cookie), re-validates the session, and lands
// on the dashboard. Wrapped in GuestGuard so an authenticated user is bounced home.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import GuestGuard from "@/app/Components/guards/GuestGuard";
import { useAuth } from "@/app/context/AuthContext";
import { ApiError, http } from "@/lib/api/apiClient";
import { t } from "@/lib/i18n/t";

function SignInForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  const { refresh } = useAuth();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await http.post("/api/auth/login", { username, password });
      refresh();
      router.replace("/");
    } catch (err) {
      const msg =
        err instanceof ApiError && err.status === 401
          ? t("signin.errInvalid")
          : t("signin.errFailed");
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-black px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-4 rounded-xl border border-slate-800 bg-slate-950/60 p-8"
      >
        <div className="space-y-1">
          <h1 className="text-lg font-semibold tracking-wide text-slate-100">SpaceHawk</h1>
          <p className="text-xs text-slate-400">{t("signin.subtitle")}</p>
        </div>
        <label className="block space-y-1">
          <span className="text-xs text-slate-400">{t("signin.username")}</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
            className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-xs text-slate-400">{t("signin.password")}</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-md bg-slate-200 py-2 text-sm font-semibold text-slate-900 transition-colors hover:bg-white disabled:opacity-50"
        >
          {busy ? t("signin.signingIn") : t("signin.signIn")}
        </button>
      </form>
    </main>
  );
}

export default function SignInPage() {
  return (
    <GuestGuard>
      <SignInForm />
    </GuestGuard>
  );
}
