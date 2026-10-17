import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const tones = {
  info: { icon: Info, cls: "border-blue-200 bg-primary-soft text-blue-900", iconCls: "text-primary" },
  success: { icon: CheckCircle2, cls: "border-green-200 bg-success-soft text-green-900", iconCls: "text-success" },
  warning: { icon: AlertTriangle, cls: "border-amber-200 bg-warning-soft text-amber-900", iconCls: "text-warning" },
  danger: { icon: XCircle, cls: "border-red-200 bg-danger-soft text-red-900", iconCls: "text-danger" },
};

type AlertProps = {
  tone?: keyof typeof tones;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
};

/** Status message. The icon and title carry meaning, not colour alone. */
export function Alert({ tone = "info", title, children, action, className }: AlertProps) {
  const { icon: Icon, cls, iconCls } = tones[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("flex gap-3 rounded-md border px-4 py-3 text-body", cls, className)}>
      <Icon className={cn("mt-0.5 size-4 shrink-0", iconCls)} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="font-medium">{title}</p>
        {children && <div className="mt-1 text-small leading-relaxed opacity-90">{children}</div>}
        {action && <div className="mt-2.5">{action}</div>}
      </div>
    </div>
  );
}
