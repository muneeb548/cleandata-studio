import { useMemo, useState, type ReactNode } from "react";
import { Calendar, Hash, Search, ToggleLeft, Type as TypeIcon, Ban, Percent } from "lucide-react";
import type { CellValue, ColumnType, DatasetKind } from "@/api/types";
import { Segmented } from "@/components/ui/segmented";
import { cn, formatCell } from "@/lib/utils";

const TYPE_META: Record<ColumnType, { label: string; icon: typeof Hash }> = {
  integer: { label: "Integer", icon: Hash },
  decimal: { label: "Decimal", icon: Percent },
  text: { label: "Text", icon: TypeIcon },
  datetime: { label: "Date/time", icon: Calendar },
  boolean: { label: "Boolean", icon: ToggleLeft },
  empty: { label: "Empty", icon: Ban },
};

export function TypeBadge({ type, className }: { type: ColumnType; className?: string }) {
  const meta = TYPE_META[type] ?? TYPE_META.text;
  return (
    <span className={cn("inline-flex items-center gap-1 text-micro font-medium text-slate-600", className)}>
      <meta.icon className="size-3" aria-hidden="true" />
      {meta.label}
    </span>
  );
}

export const typeLabel = (t: ColumnType) => (TYPE_META[t] ?? TYPE_META.text).label;

/** Renders one cell; missing values are shown with a label, not just a colour. */
export function Cell({ value, className }: { value: CellValue; className?: string }) {
  if (value === null) {
    return (
      <span className="inline-flex rounded border border-dashed border-slate-300 bg-slate-50 px-1.5 text-micro leading-4 text-slate-600 italic" title="Missing value">
        missing
      </span>
    );
  }
  const text = formatCell(value);
  if (text.trim() === "") {
    return (
      <span className="inline-flex rounded border border-dashed border-amber-300 bg-amber-50 px-1.5 text-micro leading-4 text-amber-800 italic" title={`"${text}" (only spaces)`}>
        spaces only
      </span>
    );
  }
  const padded = text !== text.trim();
  return (
    <span className={cn("block truncate", className)} title={padded ? `"${text}" (has leading/trailing spaces)` : text}>
      {padded ? <span className="rounded bg-amber-100/70 whitespace-pre">{text}</span> : text}
    </span>
  );
}

export function DatasetToggle({ value, onChange }: { value: DatasetKind; onChange: (v: DatasetKind) => void }) {
  return (
    <Segmented
      label="Dataset"
      value={value}
      onChange={onChange}
      options={[
        { value: "current", label: "Working data" },
        { value: "original", label: "Original upload" },
      ]}
    />
  );
}

type ColumnOption = { name: string; type: ColumnType; missing?: number };

type ColumnPickerProps<T extends ColumnOption> = {
  id: string;
  columns: T[];
  selected: string[];
  onChange: (next: string[]) => void;
  /** Return a reason string to disable a column (e.g. "Not numeric"). */
  disabledReason?: (col: T) => string | null;
  showMissing?: boolean;
  label?: string;
};

export function ColumnPicker<T extends ColumnOption>({ id, columns, selected, onChange, disabledReason, showMissing, label = "Columns" }: ColumnPickerProps<T>) {
  const [filter, setFilter] = useState("");
  const visible = useMemo(() => columns.filter((c) => c.name.toLowerCase().includes(filter.toLowerCase())), [columns, filter]);
  const eligible = columns.filter((c) => !disabledReason?.(c));
  const toggle = (name: string) => onChange(selected.includes(name) ? selected.filter((s) => s !== name) : [...selected, name]);

  return (
    <fieldset className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <legend className="text-small font-medium text-slate-700">
          {label} <span className="font-normal text-muted-foreground">({selected.length} selected)</span>
        </legend>
        <div className="flex gap-2 text-caption">
          <button type="button" className="font-medium text-primary hover:underline disabled:opacity-50" disabled={!eligible.length} onClick={() => onChange(eligible.map((c) => c.name))}>
            Select all{eligible.length !== columns.length ? " eligible" : ""}
          </button>
          <span className="text-border-strong" aria-hidden="true">|</span>
          <button type="button" className="font-medium text-primary hover:underline disabled:opacity-50" disabled={!selected.length} onClick={() => onChange([])}>
            Clear
          </button>
        </div>
      </div>
      {columns.length > 8 && (
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-slate-500" aria-hidden="true" />
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter columns"
            aria-label="Filter columns"
            className="h-8 w-full rounded-md border border-border-strong pr-2 pl-8 text-small"
          />
        </div>
      )}
      <div className="scroll-thin max-h-72 overflow-y-auto rounded-md border border-border">
        {visible.length === 0 && <p className="px-3 py-4 text-center text-caption text-muted-foreground">No matching columns.</p>}
        {visible.map((col, i) => {
          const reason = disabledReason?.(col) ?? null;
          const inputId = `${id}-${i}`;
          return (
            <label
              key={col.name}
              htmlFor={inputId}
              className={cn(
                "flex items-center gap-2.5 border-b border-border px-3 py-2 text-small last:border-b-0",
                reason ? "cursor-not-allowed bg-canvas text-slate-500" : "cursor-pointer hover:bg-muted",
              )}
            >
              <input
                id={inputId}
                type="checkbox"
                className="size-4 shrink-0 accent-primary"
                checked={selected.includes(col.name)}
                disabled={!!reason}
                onChange={() => toggle(col.name)}
              />
              <span className="min-w-0 flex-1 truncate font-medium" title={col.name}>
                {col.name}
              </span>
              {showMissing && typeof col.missing === "number" && col.missing > 0 && (
                <span className="tabular shrink-0 text-caption text-amber-700">{col.missing} missing</span>
              )}
              {reason ? <span className="shrink-0 text-micro">{reason}</span> : <TypeBadge type={col.type} className="shrink-0" />}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export function KeyValue({ label, value, className }: { label: string; value: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <dt className="text-caption text-muted-foreground">{label}</dt>
      <dd className="tabular mt-0.5 text-body font-medium text-foreground">{value}</dd>
    </div>
  );
}
