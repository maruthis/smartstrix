import type { ReactNode } from "react";

export function Board<T extends { id: string }>({
  columns,
  renderCard,
}: {
  columns: { key: string; label: string; items: T[] }[];
  renderCard: (item: T) => ReactNode;
}) {
  return (
    <div className="flex gap-4 overflow-x-auto pb-2">
      {columns.map((col) => (
        <div key={col.key} className="w-72 shrink-0">
          <div className="mb-2 flex items-center gap-2 px-1">
            <span className="text-xs font-medium uppercase tracking-wide text-[#888]">{col.label}</span>
            <span className="rounded-full bg-[rgba(255,255,255,0.08)] px-1.5 py-0.5 text-[10px] text-[#aaa]">{col.items.length}</span>
          </div>
          <div className="space-y-2">
            {col.items.map((item) => (
              <div key={item.id}>{renderCard(item)}</div>
            ))}
            {col.items.length === 0 && (
              <div className="rounded-lg border border-dashed border-[#222] p-4 text-center text-xs text-[#555]">Empty</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
