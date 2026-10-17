import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card } from "./card";

/** Title row at the top of every workspace view. */
export function PageHeader({ title, description, actions, className }: { title: string; description?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0">
        <h1 className="text-h1 font-semibold text-foreground">{title}</h1>
        {description && <p className="mt-1 text-body text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

type Tone = "neutral" | "warning" | "success" | "danger";
const toneIcon: Record<Tone, string> = {
  neutral: "bg-muted text-slate-500",
  warning: "bg-warning-soft text-warning",
  success: "bg-success-soft text-success",
  danger: "bg-danger-soft text-danger",
};

/** KPI tile: label, large tabular value and an optional hint. */
export function StatCard({ icon: Icon, label, value, hint, tone = "neutral", className }: { icon: LucideIcon; label: string; value: ReactNode; hint?: ReactNode; tone?: Tone; className?: string }) {
  return (
    <Card className={cn("flex flex-col gap-3 p-4", className)}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-small font-medium text-muted-foreground">{label}</p>
        <span className={cn("flex size-7 items-center justify-center rounded-md", toneIcon[tone])}>
          <Icon className="size-4" aria-hidden="true" />
        </span>
      </div>
      <div>
        <p className="tabular text-stat font-semibold text-foreground">{value}</p>
        {hint && <p className="mt-0.5 text-caption text-muted-foreground">{hint}</p>}
      </div>
    </Card>
  );
}
