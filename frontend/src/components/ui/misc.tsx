import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function Spinner({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <span role="status" className={cn("inline-flex items-center gap-2 text-body text-muted-foreground", className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
      {label}
    </span>
  );
}

export function LoadingBlock({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <div className={cn("flex min-h-40 items-center justify-center", className)}>
      <Spinner label={label} />
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      {icon && <div className="mb-3 flex size-10 items-center justify-center rounded-lg bg-muted text-slate-500 [&_svg]:size-5">{icon}</div>}
      <p className="text-body font-semibold text-foreground">{title}</p>
      {children && <div className="mt-1 max-w-sm text-body text-muted-foreground">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div>
      <div className="mb-1 flex justify-between text-caption text-muted-foreground">
        <span>{label}</span>
        <span className="tabular">{pct}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/** Small inline meter for completeness percentages. */
/** A small progress bar. `warn` turns a high value amber, e.g. a column that is full but has problems. */
export function Meter({ value, className, warn = false }: { value: number | null; className?: string; warn?: boolean }) {
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value));
  const color = pct < 70 ? "bg-danger" : pct < 95 || warn ? "bg-amber-500" : "bg-success";
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-muted", className)} aria-hidden="true">
      <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}
