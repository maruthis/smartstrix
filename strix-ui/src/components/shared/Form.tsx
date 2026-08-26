import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }) {
  const variants = {
    primary: "bg-white text-black hover:bg-white/90 disabled:bg-white/40",
    secondary: "bg-[rgba(255,255,255,0.06)] text-white border border-[#2a2a2a] hover:bg-[rgba(255,255,255,0.1)]",
    danger: "bg-red-600 text-white hover:bg-red-500 disabled:bg-red-900",
    ghost: "text-[#888] hover:text-white hover:bg-[rgba(255,255,255,0.06)]",
  };
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed",
        variants[variant],
        className
      )}
      {...props}
    />
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "w-full rounded-lg border border-[#2a2a2a] bg-black px-3 py-2 text-sm text-white placeholder:text-[#555] outline-none focus:border-[#555]",
        props.className
      )}
    />
  );
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(
        "w-full rounded-lg border border-[#2a2a2a] bg-black px-3 py-2 text-sm text-white placeholder:text-[#555] outline-none focus:border-[#555]",
        props.className
      )}
    />
  );
}

export function Select({
  value,
  onChange,
  options,
  className,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string; disabled?: boolean }[];
  className?: string;
  disabled?: boolean;
}) {
  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "rounded-lg border border-[#2a2a2a] bg-black px-3 py-2 text-sm text-white outline-none focus:border-[#555] disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function RadioGroup({
  name,
  value,
  onChange,
  options,
}: {
  name: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="flex gap-4">
      {options.map((o) => (
        <label key={o.value} className="flex cursor-pointer items-center gap-1.5 text-sm text-white">
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={value === o.value}
            onChange={() => onChange(o.value)}
            className="accent-white"
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}

export function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-block h-6 w-11 shrink-0 overflow-hidden rounded-full border border-transparent transition-colors disabled:opacity-40",
        checked ? "bg-white" : "bg-[#2a2a2a]"
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 left-0.5 h-5 w-5 rounded-full transition-transform",
          checked ? "translate-x-5 bg-black" : "translate-x-0 bg-[#888]"
        )}
      />
    </button>
  );
}

export function CheckboxGroup({
  values,
  onChange,
  options,
  minSelected = 0,
}: {
  values: string[];
  onChange: (next: string[]) => void;
  options: { value: string; label: string; description?: string }[];
  minSelected?: number;
}) {
  return (
    <div role="group" className="max-h-48 overflow-y-auto rounded-lg border border-[#2a2a2a]">
      {options.map((option) => {
        const checked = values.includes(option.value);
        const disableUncheck = checked && values.length <= minSelected;
        return (
          <label
            key={option.value}
            className="flex cursor-pointer items-start gap-2 border-b border-[#1a1a1a] px-3 py-2 last:border-0 hover:bg-[rgba(255,255,255,0.03)]"
          >
            <input
              type="checkbox"
              checked={checked}
              disabled={disableUncheck}
              onChange={() => {
                if (checked) {
                  if (values.length <= minSelected) return;
                  onChange(values.filter((value) => value !== option.value));
                  return;
                }
                onChange([...values, option.value]);
              }}
              className="mt-1 accent-white"
            />
            <span>
              <span className="block text-sm text-white">{option.label}</span>
              {option.description && <span className="block text-xs text-[#666]">{option.description}</span>}
            </span>
          </label>
        );
      })}
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="mb-4 block">
      <div className="mb-1.5 text-sm font-medium text-white">{label}</div>
      {children}
      {hint && <div className="mt-1 text-xs text-[#666]">{hint}</div>}
    </label>
  );
}
