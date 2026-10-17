import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastTone = "success" | "error" | "info";
type Toast = { id: number; tone: ToastTone; title: string; description?: string };

const ToastContext = createContext<((t: Omit<Toast, "id">) => void) | null>(null);

const icons = { success: CheckCircle2, error: XCircle, info: Info };
const iconColors = { success: "text-success", error: "text-danger", info: "text-primary" };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => setToasts((all) => all.filter((t) => t.id !== id)), []);

  const push = useCallback(
    (toast: Omit<Toast, "id">) => {
      const id = nextId.current++;
      setToasts((all) => [...all.slice(-3), { ...toast, id }]);
      window.setTimeout(() => dismiss(id), toast.tone === "error" ? 8000 : 4500);
    },
    [dismiss],
  );

  const value = useMemo(() => push, [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed right-4 bottom-4 left-4 z-50 flex flex-col items-end gap-2 sm:left-auto">
        {toasts.map((t) => {
          const Icon = icons[t.tone];
          return (
            <div
              key={t.id}
              role={t.tone === "error" ? "alert" : "status"}
              className="pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border border-border bg-background px-4 py-3 shadow-raised"
            >
              <Icon className={cn("mt-0.5 size-4 shrink-0", iconColors[t.tone])} aria-hidden="true" />
              <div className="min-w-0 flex-1 text-body">
                <p className="font-medium">{t.title}</p>
                {t.description && <p className="mt-0.5 text-small text-muted-foreground">{t.description}</p>}
              </div>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                className="-m-1 inline-flex size-7 items-center justify-center rounded text-slate-500 hover:bg-muted hover:text-slate-700"
                aria-label="Dismiss notification"
              >
                <X className="size-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
