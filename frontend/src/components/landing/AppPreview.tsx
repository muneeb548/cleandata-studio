import { AlertTriangle, Copy, Download, FileSpreadsheet, Gauge, GitCompareArrows, LayoutDashboard, Rows3, SquareDashed, Table2, WandSparkles } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Static illustration of the workspace for the landing page. It uses a small,
 * clearly labelled sample dataset — these numbers are not usage statistics.
 */
const NAV = [
  { icon: LayoutDashboard, label: "Overview", active: true },
  { icon: Table2, label: "Data preview" },
  { icon: WandSparkles, label: "Clean data" },
  { icon: GitCompareArrows, label: "Compare" },
  { icon: Download, label: "Download" },
];

const KPIS = [
  { icon: Rows3, label: "Rows", value: "1,248" },
  { icon: SquareDashed, label: "Missing cells", value: "86", warn: true },
  { icon: Copy, label: "Duplicates", value: "12", warn: true },
  { icon: Gauge, label: "Complete", value: "98.6%" },
];

const MISSING = [
  { col: "phone", pct: 100 },
  { col: "city", pct: 62 },
  { col: "amount", pct: 41 },
  { col: "signup_date", pct: 18 },
];

const ROWS: (string | null)[][] = [
  ["1001", "Ayesha Khan", "Lahore", "42,500"],
  ["1002", "  Bilal Ahmed", "lahore", null],
  ["1003", "Sara Malik", "Karachi", "38,900"],
  ["1003", "Sara Malik", "Karachi", "38,900"],
];

export function AppPreview() {
  return (
    <figure className="relative min-w-0">
      <div className="overflow-hidden rounded-xl border border-border bg-background shadow-raised" aria-hidden="true">
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <span className="flex size-5 items-center justify-center rounded bg-primary-soft text-primary">
            <FileSpreadsheet className="size-3" />
          </span>
          <span className="text-micro font-semibold text-foreground">customers.csv</span>
          <span className="hidden text-micro text-muted-foreground sm:inline">· 1,248 rows × 6 columns</span>
          <span className="ml-auto rounded bg-primary px-2 py-0.5 text-micro font-medium text-white">Download</span>
        </div>
        <div className="flex">
          <div className="hidden w-32 shrink-0 space-y-0.5 border-r border-border p-2 sm:block">
            {NAV.map((n) => (
              <div key={n.label} className={cn("flex items-center gap-1.5 rounded px-1.5 py-1 text-micro", n.active ? "bg-primary-soft font-medium text-blue-900" : "text-slate-600")}>
                <n.icon className={cn("size-3", n.active ? "text-primary" : "text-slate-500")} />
                {n.label}
              </div>
            ))}
          </div>
          <div className="min-w-0 flex-1 space-y-2.5 bg-canvas p-3">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {KPIS.map((k) => (
                <div key={k.label} className="rounded-md border border-border bg-background px-2 py-1.5">
                  <p className="flex items-center gap-1 truncate text-nano text-muted-foreground">
                    <k.icon className={cn("size-2.5 shrink-0", k.warn ? "text-warning" : "text-slate-500")} />
                    {k.label}
                  </p>
                  <p className="tabular text-small font-semibold text-foreground">{k.value}</p>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-5 gap-2">
              <div className="col-span-3 rounded-md border border-border bg-background p-2">
                <p className="mb-1.5 text-nano font-semibold text-foreground">Missing values by column</p>
                <div className="space-y-1">
                  {MISSING.map((m) => (
                    <div key={m.col} className="flex items-center gap-1.5">
                      <span className="w-14 truncate text-nano text-slate-600">{m.col}</span>
                      <span className="h-1.5 rounded-sm bg-amber-400" style={{ width: `${m.pct * 0.6}%` }} />
                    </div>
                  ))}
                </div>
              </div>
              <div className="col-span-2 rounded-md border border-border bg-background p-2">
                <p className="mb-1.5 text-nano font-semibold text-foreground">Detected issues</p>
                {["12 duplicate rows", "Extra spaces in name", "Mixed case in city"].map((t) => (
                  <p key={t} className="flex items-center gap-1 truncate py-0.5 text-nano text-slate-700">
                    <AlertTriangle className="size-2.5 shrink-0 text-warning" />
                    {t}
                  </p>
                ))}
              </div>
            </div>
            <div className="overflow-hidden rounded-md border border-border bg-background">
              <table className="w-full table-fixed text-left text-nano">
                <thead className="bg-canvas text-slate-500">
                  <tr>
                    {["id", "name", "city", "amount"].map((h) => (
                      <th key={h} className="border-b border-border px-2 py-1 font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ROWS.map((row, i) => (
                    <tr key={i} className={i === 3 ? "bg-amber-50" : undefined}>
                      {row.map((cell, j) => (
                        <td key={j} className={cn("truncate px-2 py-1 text-slate-700", i < ROWS.length - 1 && "border-b border-border")}>
                          {cell === null ? (
                            <span className="rounded border border-dashed border-slate-300 px-1 text-slate-500 italic">missing</span>
                          ) : cell.startsWith(" ") ? (
                            <span className="rounded bg-amber-100 whitespace-pre">{cell}</span>
                          ) : (
                            cell
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
      <figcaption className="mt-3 flex flex-wrap items-center justify-center gap-2 text-caption text-muted-foreground">
        <span className="rounded border border-border bg-background px-1.5 py-px text-micro font-semibold tracking-wide text-slate-500 uppercase">Demo preview</span>
        Illustration with sample data, not real usage figures.
      </figcaption>
    </figure>
  );
}
