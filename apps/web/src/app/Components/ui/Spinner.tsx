// Minimal full-screen loading indicator used by the auth guards while the
// session is being validated (mirrors the reference guards' <Spinner/>).

import { t } from "@/lib/i18n/t";

export default function Spinner() {
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
