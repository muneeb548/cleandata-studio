import type { HTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-caption font-medium whitespace-nowrap [&_svg]:size-3",
  {
    variants: {
      tone: {
        neutral: "border-border bg-muted text-slate-700",
        primary: "border-blue-200 bg-primary-soft text-blue-800",
        accent: "border-indigo-200 bg-accent-soft text-indigo-800",
        success: "border-green-200 bg-success-soft text-green-800",
        warning: "border-amber-200 bg-warning-soft text-amber-800",
        danger: "border-red-200 bg-danger-soft text-red-800",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({ className, tone, ...props }: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
