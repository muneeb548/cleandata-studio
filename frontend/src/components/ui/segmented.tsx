import { cn } from "@/lib/utils";

type Option<T extends string> = { value: T; label: string; disabled?: boolean };

/** Compact switch between a few views (e.g. working data / original upload). */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  className,
}: {
  value: T;
  onChange: (value: T) => void;
  options: Option<T>[];
  label: string;
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("inline-flex rounded-md border border-border bg-muted p-0.5", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          disabled={o.disabled}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-[5px] px-3 py-1 text-small font-medium whitespace-nowrap transition-colors disabled:opacity-50",
            value === o.value ? "bg-background text-foreground shadow-card" : "text-slate-600 hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
