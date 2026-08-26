import { Kanban, List } from "lucide-react";
import { cn } from "../../lib/cn";

export type ViewMode = "list" | "board";

export function ViewToggle({ view, onChange }: { view: ViewMode; onChange: (v: ViewMode) => void }) {
  return (
    <div className="inline-flex rounded-lg border border-[#2a2a2a] p-0.5">
      <button
        onClick={() => onChange("list")}
        className={cn("flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs", view === "list" ? "bg-[rgba(255,255,255,0.1)] text-white" : "text-[#888]")}
      >
        <List size={13} /> List
      </button>
      <button
        onClick={() => onChange("board")}
        className={cn("flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs", view === "board" ? "bg-[rgba(255,255,255,0.1)] text-white" : "text-[#888]")}
      >
        <Kanban size={13} /> Board
      </button>
    </div>
  );
}
