import { cn } from "../../lib/cn";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "text-red-400 bg-red-500/10 border-red-500/30",
  high: "text-orange-400 bg-orange-500/10 border-orange-500/30",
  medium: "text-yellow-400 bg-yellow-500/10 border-yellow-500/30",
  low: "text-blue-400 bg-blue-500/10 border-blue-500/30",
};

const STATUS_COLORS: Record<string, string> = {
  enabled: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  active: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  completed: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  passed: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  fixed: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  verified: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  disabled: "text-[#888] bg-[rgba(255,255,255,0.04)] border-[#333]",
  ignored: "text-[#888] bg-[rgba(255,255,255,0.04)] border-[#333]",
  revoked: "text-[#888] bg-[rgba(255,255,255,0.04)] border-[#333]",
  running: "text-blue-400 bg-blue-500/10 border-blue-500/30",
  queued: "text-[#888] bg-[rgba(255,255,255,0.04)] border-[#333]",
  in_progress: "text-blue-400 bg-blue-500/10 border-blue-500/30",
  awaiting_merge: "text-[#888] bg-[rgba(255,255,255,0.04)] border-[#333]",
  needs_attention: "text-orange-400 bg-orange-500/10 border-orange-500/30",
  merged_with_open_findings: "text-red-400 bg-red-500/10 border-red-500/30",
  snoozed: "text-yellow-400 bg-yellow-500/10 border-yellow-500/30",
  failed: "text-red-400 bg-red-500/10 border-red-500/30",
  trialing: "text-blue-400 bg-blue-500/10 border-blue-500/30",
  baseline_scan: "text-purple-400 bg-purple-500/10 border-purple-500/30",
  mock_fallback: "text-amber-400 bg-amber-500/10 border-amber-500/30",
};

export function StatusPill({ value, label }: { value: string; label?: string }) {
  const cls = SEVERITY_COLORS[value] ?? STATUS_COLORS[value] ?? "text-[#888] bg-[rgba(255,255,255,0.04)] border-[#333]";
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize", cls)}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label ?? value.replace(/_/g, " ")}
    </span>
  );
}
