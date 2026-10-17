import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * tailwind-merge must know our custom type-scale names (see index.css);
 * otherwise it treats `text-small` as a colour and drops it next to `text-slate-600`.
 */
export const TYPE_SCALE = ["display", "h1", "h2", "h3", "body", "small", "caption", "micro", "nano", "stat"];
const twMerge = extendTailwindMerge({ extend: { theme: { text: TYPE_SCALE } } });

/** Merge Tailwind class names, letting later classes override earlier ones. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const numberFormat = new Intl.NumberFormat("en-US");

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return numberFormat.format(value);
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "N/A";
  return `${value.toFixed(digits)}%`;
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(12)));
  return String(value);
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${formatNumber(count)} ${count === 1 ? singular : plural}`;
}

/** Signed difference such as "+3" / "−12" / "0". */
export function formatDelta(after: number, before: number): string {
  const d = after - before;
  if (d === 0) return "0";
  return d > 0 ? `+${formatNumber(d)}` : `−${formatNumber(Math.abs(d))}`;
}

/** Client-side mirror of the backend's output filename rules (for the input hint). */
export function suggestedOutputName(originalName: string): string {
  const stem = originalName.replace(/\.(csv|tsv|tab|xlsx|xlsm|xls|json|jsonl|ndjson)$/i, "");
  return `${stem}_cleaned`;
}

export const SUPPORTED_EXTENSIONS = [".csv", ".tsv", ".tab", ".xlsx", ".xlsm", ".xls", ".json", ".jsonl", ".ndjson"];

/** Import format implied by a file name, or null when the type is not supported. */
export function formatFromName(name: string): "csv" | "tsv" | "xlsx" | "xls" | "json" | null {
  const ext = (/\.[^.]+$/.exec(name.toLowerCase()) ?? [""])[0];
  if (ext === ".csv") return "csv";
  if (ext === ".tsv" || ext === ".tab") return "tsv";
  if (ext === ".xlsx" || ext === ".xlsm") return "xlsx";
  if (ext === ".xls") return "xls";
  if (ext === ".json" || ext === ".jsonl" || ext === ".ndjson") return "json";
  return null;
}

export function isSupportedFile(file: File): boolean {
  return formatFromName(file.name) !== null;
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}
