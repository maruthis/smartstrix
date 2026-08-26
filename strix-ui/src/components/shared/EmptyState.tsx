import type { ReactNode } from "react";

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] py-20 text-center">
      {icon && <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[rgba(255,255,255,0.06)] text-[#888]">{icon}</div>}
      <div className="text-[15px] font-medium text-white">{title}</div>
      {description && <div className="max-w-sm text-sm text-[#888]">{description}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function QueryStatus({ isLoading }: { isLoading: boolean }) {
  if (isLoading) return <p className="text-sm text-[#666]">Loading…</p>;
  return <p className="text-sm text-[#888]">Couldn't load this page. It may not exist, or you may not have access.</p>;
}
