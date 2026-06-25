// Centered "nothing to see here" panel. Used by AdminGuard to deny non-admins
// without revealing the page (the reference AdminGuard's 404 / "Ask Admin").

export default function EmptyState({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <div className="fixed inset-0 flex flex-col items-center justify-center gap-2 bg-black text-center">
      <h1 className="text-2xl font-semibold text-slate-200">{title}</h1>
      <p className="max-w-sm text-sm text-slate-400">{message}</p>
    </div>
  );
}
