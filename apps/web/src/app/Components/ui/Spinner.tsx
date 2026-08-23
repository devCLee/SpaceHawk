// Minimal full-screen loading indicator used by the auth guards while the
// session is being validated (mirrors the reference guards' <Spinner/>),
// plus the shadcn/ui base Spinner for inline loading states.

import type { ComponentProps } from "react";
import { t } from "@/lib/i18n/t";
import { cn } from "@/lib/utils";

/** shadcn/ui base Spinner — lucide LoaderCircle inlined (no icon dependency). */
export function Spinner({ className, ...props }: ComponentProps<"svg">) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      role="status"
      aria-label={t("common.loadingAria")}
      className={cn("size-4 animate-spin", className)}
      {...props}
    >
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}

export default function FullScreenSpinner() {
  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black">
      <div
        className="h-8 w-8 animate-spin rounded-full border-2 border-slate-600 border-t-slate-200"
        role="status"
        aria-label={t("common.loadingAria")}
      />
    </div>
  );
}
