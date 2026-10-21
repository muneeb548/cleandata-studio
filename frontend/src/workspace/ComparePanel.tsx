import { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, Columns3, GitCompareArrows, PencilLine, Rows3, SearchX, SquareDashed } from "lucide-react";
import { api } from "@/api/client";
import type { CompareRowsPage, Quality, Stats } from "@/api/types";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/form";
import { EmptyState, LoadingBlock, Spinner } from "@/components/ui/misc";
import { PageHeader, StatCard } from "@/components/ui/page";
import { Segmented } from "@/components/ui/segmented";
import { RowNumberCell, Table, TableContainer, TD, TH, THead, TR } from "@/components/ui/table";
import { cn, formatDelta, formatNumber, formatPercent, pluralize } from "@/lib/utils";
import { Pagination, RowsTable } from "./DataPanel";
import { Cell } from "./shared";
import { useAsync } from "./useAsync";
import { useWorkspace } from "./WorkspaceContext";

type Metrics = Stats & { problems?: number };

const METRICS: { key: keyof Metrics; label: string; better: "lower" | "higher" | "neutral"; pct?: boolean }[] = [
  { key: "rows", label: "Rows", better: "neutral" },
  { key: "columns", label: "Columns", better: "neutral" },
  { key: "missing_cells", label: "Missing cells", better: "lower" },
  { key: "duplicate_rows", label: "Duplicate rows", better: "lower" },
  { key: "columns_with_missing", label: "Columns with missing values", better: "lower" },
  { key: "empty_rows", label: "Completely empty rows", better: "lower" },
  { key: "completeness", label: "Completeness", better: "higher", pct: true },
  { key: "problems", label: "Problems found", better: "lower" },
];

/**
 * Plain stats count only truly empty cells, so turning "N/A" into an empty cell would look
 * like the data got worse. The server's quality numbers count "N/A"-style cells as missing
 * on both sides, the same way the Overview does.
 */
export function withQuality(stats: Stats, quality?: Quality): Metrics {
  return quality ? { ...stats, ...quality } : stats;
}

const PAGE_SIZE = 50;

/** One table: current values, with changed cells showing the original underneath. */
function InlineDiff({ data }: { data: CompareRowsPage }) {
  const origPos = new Map(data.original_columns.map((c, i) => [c, i]));
  return (
    <TableContainer label="Row comparison, changes highlighted" maxHeight="max-h-[62vh]">
      <Table className="w-max min-w-full">
        <THead>
          <tr>
            <TH scope="col" className="sticky left-0 z-20 border-r text-right">
              #
            </TH>
            {data.current_columns.map((c) => (
              <TH key={c} scope="col">
                <span className="block max-w-60 truncate text-small font-semibold text-slate-800" title={c}>
                  {c}
                </span>
                {data.renamed_or_new.includes(c) && <span className="text-micro font-normal text-slate-500">renamed or new</span>}
              </TH>
            ))}
          </tr>
        </THead>
        <tbody>
          {data.rows.map((r) =>
            r.current === null ? (
              <TR key={r.row} className="bg-red-50/60 hover:bg-red-50">
                <RowNumberCell className="bg-red-50">{r.row}</RowNumberCell>
                {data.current_columns.map((c, j) => {
                  const pos = origPos.get(c);
                  return (
                    <TD key={c} className="max-w-72 py-1.5 text-red-900/70 line-through decoration-red-300">
                      {j === 0 && (
                        <Badge tone="danger" className="mr-2 no-underline">
                          Removed
                        </Badge>
                      )}
                      {pos === undefined ? "—" : <Cell value={r.original[pos]} className="inline" />}
                    </TD>
                  );
                })}
              </TR>
            ) : (
              <TR key={r.row}>
                <RowNumberCell>{r.row}</RowNumberCell>
                {r.current.map((v, j) => {
                  const changed = r.changed?.[j];
                  const pos = origPos.get(data.current_columns[j]);
                  return (
                    <TD key={j} className={cn("max-w-72 py-1.5", changed && "bg-blue-50/70")}>
                      {changed ? (
                        <div className="min-w-0">
                          <span className="font-medium text-foreground">
                            <Cell value={v} />
                          </span>
                          <span className="flex items-center gap-1 text-micro text-slate-500">
                            <span className="shrink-0">was</span>
                            <span className="min-w-0 line-through decoration-slate-300">
                              <Cell value={pos === undefined ? null : r.original[pos]} />
                            </span>
                          </span>
                        </div>
                      ) : (
                        <Cell value={v} />
                      )}
                    </TD>
                  );
                })}
              </TR>
            ),
          )}
        </tbody>
      </Table>
    </TableContainer>
  );
}

function SideBySide({ data }: { data: CompareRowsPage }) {
  const numbers = data.rows.map((r) => r.row);
  const removed = (i: number) => data.rows[i].current === null;
  return (
    <div className="grid divide-y divide-border xl:grid-cols-2 xl:divide-x xl:divide-y-0">
      <div className="min-w-0">
        <p className="eyebrow border-b border-border bg-background px-4 py-2">Original upload</p>
        <RowsTable
          columns={data.original_columns.map((name) => ({ name }))}
          rows={data.rows.map((r) => r.original)}
          rowNumbers={numbers}
          caption="Original rows"
          maxHeight="max-h-[60vh]"
          rowClassName={(i) => (removed(i) ? "bg-red-50/60" : undefined)}
        />
      </div>
      <div className="min-w-0">
        <p className="eyebrow border-b border-border bg-background px-4 py-2">Current working data</p>
        <RowsTable
          columns={data.current_columns.map((name) => ({ name }))}
          rows={data.rows.map((r) => r.current ?? data.current_columns.map(() => null))}
          rowNumbers={numbers}
          caption="Current rows"
          maxHeight="max-h-[60vh]"
          rowClassName={(i) => (removed(i) ? "bg-red-50/60" : undefined)}
          renderCell={(i, j) => {
            const r = data.rows[i];
            if (r.current === null) return j === 0 ? <Badge tone="danger">Removed</Badge> : <span className="text-slate-300">—</span>;
            return r.changed?.[j] ? (
              <span className="-mx-1.5 block rounded bg-blue-50 px-1.5 font-medium text-foreground">
                <Cell value={r.current[j]} />
              </span>
            ) : undefined;
          }}
        />
      </div>
    </div>
  );
}

function RowComparison() {
  const { version } = useWorkspace();
  const [mode, setMode] = useState<"inline" | "side">("inline");
  const [changesOnly, setChangesOnly] = useState(true);
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [version, changesOnly]);
  const { data, error, loading, reload } = useAsync(() => api.compareRows(page, PAGE_SIZE, changesOnly), [page, changesOnly, version], version);

  return (
    <Card className="overflow-hidden">
      <CardHeader className="gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle>Row comparison</CardTitle>
          <CardDescription>Rows are matched by their position in the uploaded file. Changed cells are highlighted in blue, removed rows in red.</CardDescription>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Checkbox id="changes-only" checked={changesOnly} onChange={(e) => setChangesOnly(e.target.checked)} label="Only changed rows" />
          <Segmented
            label="Comparison layout"
            value={mode}
            onChange={setMode}
            options={[
              { value: "inline", label: "Highlighted" },
              { value: "side", label: "Side by side" },
            ]}
          />
        </div>
      </CardHeader>
      {error && !data && (
        <div className="p-4">
          <Alert tone="danger" title={error.message} action={<Button size="sm" variant="secondary" onClick={reload}>Retry</Button>}>
            {error.hint}
          </Alert>
        </div>
      )}
      {!data && loading && <LoadingBlock label="Comparing rows…" />}
      {data && data.rows.length === 0 && (
        <EmptyState icon={<SearchX />} title={changesOnly ? "No rows were changed or removed" : "No rows to compare"}>
          {changesOnly ? "The applied operations only renamed columns or changed nothing row-specific." : undefined}
        </EmptyState>
      )}
      {data && data.rows.length > 0 && (mode === "inline" ? <InlineDiff data={data} /> : <SideBySide data={data} />)}
      {data && data.total_rows > 0 && (
        <div className="flex flex-col items-center justify-between gap-3 border-t border-border bg-canvas px-4 py-2.5 sm:flex-row">
          <p className="tabular flex items-center gap-2 text-small text-muted-foreground">
            {formatNumber(data.total_rows)} {changesOnly ? "changed or removed" : "original"} {data.total_rows === 1 ? "row" : "rows"}
            {loading && <Spinner label="Updating" />}
          </p>
          <Pagination page={data.page} totalPages={data.total_pages} onPage={setPage} />
        </div>
      )}
    </Card>
  );
}

export function ComparePanel() {
  const { version, setTab } = useWorkspace();
  const { data, error, loading, reload } = useAsync(() => api.compare(), [version], version);
  const header = <PageHeader title="Compare" description="The original upload compared with the current working data. All figures are calculated from the data." />;

  if (!data && loading)
    return (
      <div className="space-y-6">
        {header}
        <LoadingBlock label="Comparing datasets…" />
      </div>
    );
  if (!data) {
    return (
      <div className="space-y-6">
        {header}
        <Alert tone="danger" title={error?.message ?? "Could not load the comparison"} action={<Button size="sm" variant="secondary" onClick={reload}>Retry</Button>}>
          {error?.hint}
        </Alert>
      </div>
    );
  }

  if (data.operations.length === 0) {
    return (
      <div className="space-y-6">
        {header}
        <Card>
          <EmptyState icon={<GitCompareArrows />} title="No changes yet" action={<Button onClick={() => setTab("clean")}>Start cleaning</Button>}>
            Apply at least one cleaning operation to compare the result with your original upload.
          </EmptyState>
        </Card>
      </div>
    );
  }

  const o = withQuality(data.original, data.quality?.original);
  const c = withQuality(data.current, data.quality?.current);
  return (
    <div className="space-y-6">
      {header}

      <section aria-label="Change summary" className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard icon={Rows3} label="Rows removed" value={formatNumber(data.rows_removed)} hint={`${formatNumber(o.rows)} → ${formatNumber(c.rows)} rows`} />
        <StatCard icon={Columns3} label="Columns removed" value={formatNumber(data.columns_removed)} hint={`${formatNumber(o.columns)} → ${formatNumber(c.columns)} columns`} />
        <StatCard icon={PencilLine} label="Cells modified" value={formatNumber(data.cells_modified)} hint="across all operations" />
        <StatCard
          icon={SquareDashed}
          label="Missing cells"
          value={formatNumber(c.missing_cells)}
          hint={c.missing_cells === o.missing_cells ? `no change (was ${formatNumber(o.missing_cells)})` : `was ${formatNumber(o.missing_cells)} (${formatDelta(c.missing_cells, o.missing_cells)})`}
          tone={c.missing_cells < o.missing_cells ? "success" : "neutral"}
        />
      </section>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Quality metrics</CardTitle>
            <CardDescription>
              Original upload versus current working data. "N/A", "null" and space-only cells count as missing on both sides, as in the Overview.
            </CardDescription>
          </CardHeader>
          <TableContainer label="Quality metrics">
            <Table className="min-w-[420px]">
              <THead sticky={false}>
                <tr>
                  <TH scope="col" className="pl-5">Metric</TH>
                  <TH scope="col" className="text-right">Original</TH>
                  <TH scope="col" className="text-right">Current</TH>
                  <TH scope="col" className="pr-5 text-right">Change</TH>
                </tr>
              </THead>
              <tbody>
                {METRICS.filter((m) => o[m.key] !== undefined && c[m.key] !== undefined).map((m) => {
                  const before = o[m.key] as number | null;
                  const after = c[m.key] as number | null;
                  const fmt = (v: number | null) => (m.pct ? formatPercent(v) : formatNumber(v));
                  let delta = "—";
                  let improved: boolean | null = null;
                  if (before !== null && after !== null) {
                                       const diff = m.pct ? Math.round((after - before) * 10) / 10 : after - before;
                    delta = m.pct ? (diff === 0 ? "0 pts" : `${diff > 0 ? "+" : "−"}${Math.abs(diff).toFixed(1)} pts`) : formatDelta(after, before);
                    if (diff !== 0 && m.better !== "neutral") improved = m.better === "lower" ? after < before : after > before;
                  }
                  return (
                    <TR key={m.key}>
                      <TD className="pl-5 font-medium text-foreground">{m.label}</TD>
                      <TD className="tabular text-right text-slate-500">{fmt(before)}</TD>
                      <TD className="tabular text-right font-medium text-foreground">{fmt(after)}</TD>
                      <TD className={cn("tabular pr-5 text-right", improved === true && "text-success", improved === false && "text-danger")}>
                        {delta}
                        {improved !== null && <span className="sr-only">{improved ? " (improved)" : " (worse)"}</span>}
                      </TD>
                    </TR>
                  );
                })}
              </tbody>
            </Table>
          </TableContainer>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>What each operation changed</CardTitle>
            <CardDescription>{pluralize(data.operations.length, "operation")} applied, in order.</CardDescription>
          </CardHeader>
          <ol className="scroll-thin max-h-96 divide-y divide-border overflow-y-auto">
            {data.operations.map((op, i) => (
              <li key={op.id} className="flex gap-3 px-5 py-3">
                <span className="tabular flex size-6 shrink-0 items-center justify-center rounded-full bg-success-soft text-caption font-semibold text-green-800">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-1.5 text-small font-medium">
                    <CheckCircle2 className="size-3.5 shrink-0 text-success" aria-hidden="true" />
                    {op.label}
                  </p>
                  <p className="mt-0.5 text-caption text-muted-foreground">{op.summary}</p>
                  <p className="tabular mt-1 flex items-center gap-1 text-micro text-slate-500">
                    {formatNumber(op.rows_before)} × {op.columns_before}
                    <ArrowRight className="size-3" aria-label="to" />
                    {formatNumber(op.rows_after)} × {op.columns_after}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <RowComparison />
    </div>
  );
}
