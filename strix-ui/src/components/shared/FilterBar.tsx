import { Search } from "lucide-react";
import type { ReactNode } from "react";

export function FilterBar({
  search,
  onSearch,
  placeholder = "Search...",
  children,
}: {
  search?: string;
  onSearch?: (v: string) => void;
  placeholder?: string;
  children?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      {onSearch && (
        <div className="relative min-w-[220px] flex-1">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#666]" />
          <input
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder={placeholder}
            className="w-full rounded-lg border border-[#2a2a2a] bg-black py-2 pl-9 pr-3 text-sm text-white placeholder:text-[#555] outline-none focus:border-[#555]"
          />
        </div>
      )}
      {children}
    </div>
  );
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: string; label: string; count?: number }[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="mb-4 flex items-center gap-1 border-b border-[#1a1a1a]">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className={`flex items-center gap-2 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
            active === tab.key ? "border-white text-white" : "border-transparent text-[#888] hover:text-white"
          }`}
        >
          {tab.label}
          {tab.count !== undefined && (
            <span className="rounded-full bg-[rgba(255,255,255,0.08)] px-1.5 py-0.5 text-xs text-[#aaa]">{tab.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}
