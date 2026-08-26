import { create } from "zustand";
import { CheckCircle2, XCircle, X } from "lucide-react";
import { cn } from "../../lib/cn";

interface ToastItem {
  id: number;
  message: string;
  type: "success" | "error";
}

interface ToastState {
  toasts: ToastItem[];
  push: (message: string, type: ToastItem["type"]) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;

const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  push: (message, type) => {
    const id = nextId++;
    set({ toasts: [...get().toasts, { id, message, type }] });
    setTimeout(() => get().dismiss(id), 4500);
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}));

export const toast = {
  success: (message: string) => useToastStore.getState().push(message, "success"),
  error: (message: string) => useToastStore.getState().push(message, "error"),
};

export function Toaster() {
  const { toasts, dismiss } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            "fade-in flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm shadow-xl",
            t.type === "success" ? "border-emerald-900/50 bg-[#0a0a0a] text-emerald-200" : "border-red-900/50 bg-[#0a0a0a] text-red-200"
          )}
        >
          {t.type === "success" ? (
            <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-400" />
          ) : (
            <XCircle size={16} className="mt-0.5 shrink-0 text-red-400" />
          )}
          <span className="flex-1 text-[#ddd]">{t.message}</span>
          <button onClick={() => dismiss(t.id)} className="text-[#666] hover:text-white">
            <X size={13} />
          </button>
        </div>
      ))}
    </div>
  );
}
