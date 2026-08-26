import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "../../lib/cn";

export function ListSelect({
  value,
  onChange,
  options,
  className,
  ariaLabel,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  className?: string;
  ariaLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const onClickAway = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickAway);
    return () => document.removeEventListener("mousedown", onClickAway);
  }, [open]);

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <button
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-[#2a2a2a] bg-black px-3 py-2 text-left text-sm text-white outline-none focus:border-[#555]"
      >
        <span className="truncate">{selected?.label ?? ""}</span>
        <ChevronDown size={14} className="shrink-0 text-[#666]" />
      </button>
      {open && (
        <div
          role="listbox"
          aria-label={ariaLabel}
          className="absolute z-20 mt-1.5 max-h-64 w-full min-w-[16rem] overflow-y-auto rounded-lg border border-[#2a2a2a] bg-[#0a0a0a] p-1 shadow-2xl"
        >
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              role="option"
              aria-selected={o.value === value}
              onClick={() => {
                onChange(o.value);
                setOpen(false);
              }}
              className={cn(
                "flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left text-sm break-words whitespace-normal hover:bg-[rgba(255,255,255,0.06)]",
                o.value === value ? "text-white" : "text-[#aaa]"
              )}
            >
              <Check size={14} className={cn("mt-0.5 shrink-0", o.value === value ? "opacity-100" : "opacity-0")} />
              <span>{o.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
