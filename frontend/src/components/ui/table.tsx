import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/**
 * Table primitives used by every table in the product, so headers, row
 * separators and spacing look identical everywhere.
 */
export function TableContainer({ className, label, children, maxHeight }: { className?: string; label: string; children: ReactNode; maxHeight?: string }) {
  return (
    <div className={cn("relative scroll-thin overflow-auto", maxHeight, className)} tabIndex={0} role="region" aria-label={label}>
      {children}
    </div>
  );
}

export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return <table className={cn("w-full border-separate border-spacing-0 text-small", className)} {...props} />;
}

export function THead({ className, sticky = true, ...props }: HTMLAttributes<HTMLTableSectionElement> & { sticky?: boolean }) {
  return <thead className={cn("bg-canvas", sticky && "sticky top-0 z-10", className)} {...props} />;
}

export function TH({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn("border-b border-border bg-canvas px-3 py-2 text-left align-bottom text-caption font-medium whitespace-nowrap text-slate-600", className)}
      {...props}
    />
  );
}

export function TR({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("transition-colors hover:bg-slate-50/70", className)} {...props} />;
}

export function TD({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("border-b border-border px-3 py-2 align-top text-slate-700", className)} {...props} />;
}

/** Row-number cell that stays visible while scrolling horizontally. */
export function RowNumberCell({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <th scope="row" className={cn("tabular sticky left-0 z-[1] border-r border-b border-border bg-background px-3 py-2 text-right text-caption font-normal text-slate-500", className)}>
      {children}
    </th>
  );
}
