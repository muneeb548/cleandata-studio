import { useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Columns3,
  Copy,
  Gauge,
  Info,
  Rows3,
  SquareDashed,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell as ChartCell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/api/client";
import type { ColumnType, DatasetKind, Issue, Profile, Severity } from "@/api/types";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, LoadingBlock, Meter } from "@/components/ui/misc";
import { PageHeader, StatCard } from "@/components/ui/page";
import { Table, TableContainer, TD, TH, THead, TR } from "@/components/ui/table";
import { cn, formatNumber, formatPercent, pluralize } from "@/lib/utils";
import { AskAiButton, ChatWithDataButton } from "./Ai";
import { QuickCleanButton } from "./QuickClean";
import { ApplyRecipeButton, ResumeBanner } from "./Recipes";
import { DatasetToggle, TypeBadge, typeLabel } from "./shared";
import { useAsync } from "./useAsync";
import { useWorkspace } from "./WorkspaceContext";

// Keep in sync with --color-chart-* in index.css (Recharts needs literal colours).
const TYPE_COLORS: Record<ColumnType, string> = {
  text: "#2563eb",
  integer: "#4f46e5",
  decimal: "#0891b2",
  datetime: "#7c3aed",
  boolean: "#0d9488",
  empty: "#94a3b8",
};

const SEVERITY: Record<Severity, { label: string; tone: "danger" | "warning" | "neutral" | "primary"; icon: LucideIcon; color: string }> = {
  high: { label: "High", tone: "danger", icon: AlertCircle, color: "text-danger" },
  medium: { label: "Medium", tone: "warning", icon: AlertTriangle, color: "text-warning" },
  low: { label: "Low", tone: "neutral", icon: Info, color: "text-slate-500" },
  info: { label: "Review", tone: "primary", icon: Info, color: "text-primary" },
};

const ISSUE_PREVIEW = 6;

function IssueRow({ issue }: { issue: Issue }) {
  const { openOperation } = useWorkspace();
  const sev = SEVERITY[issue.severity];
  return (
    <li className="flex items-start gap-3 px-5 py-3">
      <sev.icon className={cn("mt-0.5 size-4 shrink-0", sev.color)} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-small font-medium text-foreground">
          <span className="break-words">{issue.title}</span>
          <Badge tone={sev.tone}>{sev.label}</Badge>
        </p>
        <p className="mt-0.5 text-caption text-muted-foreground">{issue.description}</p>
      </div>
      {issue.suggested_operation && (
        <Button variant="secondary" size="sm" className="shrink-0" onClick={() => openOperation(issue.suggested_operation!, issue.column, issue.id, issue.example)}>
          <Wrench /> {issue.suggested_operation === "outliers" ? "Review" : "Fix"}
        </Button>
      )}
    </li>
  );
}

function QualitySummary({ profile, applied }: { profile: Profile; applied: number }) {
  const { setTab } = useWorkspace();
  const s = profile.stats;
  const counts: Record<Severity, number> = { high: 0, medium: 0, low: 0, info: 0 };
  profile.issues.forEach((i) => counts[i.severity]++);
  const pct = profile.health?.real_completeness ?? s.completeness;
  const looksEmpty = profile.health?.looks_empty_cells ?? 0;
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardTitle>Data quality summary</CardTitle>
        <CardDescription>Calculated from every cell of this dataset.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-5">
        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-small text-muted-foreground">Completeness</span>
            <span className="tabular text-stat font-semibold">{formatPercent(pct)}</span>
          </div>
          <Meter value={pct} className="mt-2 h-2" />
          <p className="mt-2 text-caption text-muted-foreground">
            {s.total_cells
              ? `${formatNumber(s.total_cells - s.missing_cells - looksEmpty)} of ${formatNumber(s.total_cells)} cells have a real value.${looksEmpty ? ` ${pluralize(looksEmpty, "cell")} only say "N/A", "null" or similar.` : ""}`
              : "The dataset has no cells."}
          </p>
        </div>
        <dl className="divide-y divide-border rounded-md border border-border">
          {(Object.keys(SEVERITY) as Severity[]).map((sev) => {
            const meta = SEVERITY[sev];
            return (
              <div key={sev} className="flex items-center justify-between px-3 py-2 text-small">
                <dt className="flex items-center gap-2 text-slate-700">
                  <meta.icon className={cn("size-4", meta.color)} aria-hidden="true" />
                  {sev === "info" ? "To review" : `${meta.label} priority`}
                </dt>
                <dd className="tabular font-semibold">{counts[sev]}</dd>
              </div>
            );
          })}
        </dl>
        <div className="mt-auto flex items-center justify-between gap-3 text-small">
          <span className="text-muted-foreground">{applied ? `${pluralize(applied, "operation")} applied` : "No operations applied yet"}</span>
          <Button variant="link" size="sm" onClick={() => setTab(applied ? "compare" : "clean")}>
            {applied ? "Compare" : "Start cleaning"} <ArrowRight />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function MissingChart({ profile }: { profile: Profile }) {
  const data = profile.columns
    .filter((c) => c.missing > 0)
    .sort((a, b) => b.missing - a.missing)
    .slice(0, 10)
    .map((c) => ({ name: c.name.length > 18 ? `${c.name.slice(0, 17)}…` : c.name, full: c.name, missing: c.missing, pct: c.missing_pct }));
  if (!data.length) {
    return (
      <EmptyState icon={<CheckCircle2 />} title="No missing values" className="py-10">
        Every cell in this dataset has a value.
      </EmptyState>
    );
  }
  return (
    <div style={{ height: Math.max(180, data.length * 32 + 32) }} role="img" aria-label={`Missing values by column: ${data.map((d) => `${d.full} ${d.missing}`).join(", ")}`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
          <CartesianGrid horizontal={false} stroke="#eef2f6" />
          <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey="name" width={128} tick={{ fontSize: 12, fill: "#334155" }} axisLine={false} tickLine={false} />
          <Tooltip
            cursor={{ fill: "#f1f5f9" }}
            contentStyle={{ borderRadius: 6, border: "1px solid #e2e8f0", fontSize: 12, boxShadow: "0 4px 16px -4px rgb(15 23 42 / 0.12)" }}
            formatter={(value: unknown, _n: unknown, item: { payload?: unknown }) => [`${formatNumber(Number(value))} (${(item.payload as { pct: number }).pct}%)`, "Missing"]}
            labelFormatter={(_l: unknown, payload?: readonly { payload?: unknown }[]) => (payload?.[0]?.payload as { full?: string } | undefined)?.full ?? ""}
          />
          <Bar dataKey="missing" fill="#f59e0b" radius={[0, 3, 3, 0]} barSize={14} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function TypeSummary({ profile }: { profile: Profile }) {
  const data = (Object.entries(profile.type_distribution) as [ColumnType, number][])
    .sort((a, b) => b[1] - a[1])
    .map(([type, count]) => ({ type, label: typeLabel(type), count }));
  const total = data.reduce((n, d) => n + d.count, 0);
  if (!data.length) return <EmptyState title="No columns" className="py-10" />;
  return (
    <div className="flex items-center gap-5">
      <div className="size-28 shrink-0" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="count" nameKey="label" innerRadius={34} outerRadius={54} paddingAngle={2} stroke="none" isAnimationActive={false}>
              {data.map((d) => (
                <ChartCell key={d.type} fill={TYPE_COLORS[d.type]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="min-w-0 flex-1 space-y-2 text-small">
        {data.map((d) => (
          <li key={d.type} className="flex items-center gap-2">
            <span className="size-2.5 shrink-0 rounded-sm" style={{ background: TYPE_COLORS[d.type] }} aria-hidden="true" />
            <span className="flex-1 text-slate-700">{d.label}</span>
            <span className="tabular font-medium">{d.count}</span>
            <span className="tabular w-10 text-right text-caption text-muted-foreground">{Math.round((d.count / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The problems (not notes) found in one column, without the repeated ' in "column"' ending. */
export function problemTitles(issues: Issue[], column: string): string[] {
  const suffix = ` in "${column}"`;
  return issues
    .filter((i) => i.column === column && i.severity !== "info")
    .map((i) => (i.title.endsWith(suffix) ? i.title.slice(0, -suffix.length) : i.title));
}

function ColumnProblems({ count, titles }: { count: number; titles: string[] }) {
  return (
    <div className="min-w-0 max-w-64">
      <Badge tone="warning">{pluralize(count, "problem")}</Badge>
      {titles.length > 0 && (
        <ul className="mt-1 space-y-0.5 text-caption text-slate-600">
          {titles.map((t, i) => (
            <li key={i} className="truncate" title={t}>
              {t}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function OverviewPanel() {
  const { version, info } = useWorkspace();
  const [dataset, setDataset] = useState<DatasetKind>("current");
  const [showAll, setShowAll] = useState(false);
  const { data: profile, error, loading, reload } = useAsync(() => api.profile(dataset), [dataset, version], version);
  const applied = info?.history.length ?? 0;

  const header = (
    <>
    <PageHeader
      title="Overview"
      description={
        dataset === "original"
          ? "Quality report for the file exactly as uploaded."
          : applied
            ? `Quality report after ${pluralize(applied, "applied operation")}.`
            : "Quality report for your uploaded data. Nothing has been changed yet."
      }
      actions={
        <div className="flex flex-wrap items-center gap-2">
          {dataset === "current" && <ApplyRecipeButton />}
          {dataset === "current" && <ChatWithDataButton />}
          {dataset === "current" && <AskAiButton />}
          {dataset === "current" && <QuickCleanButton />}
          <DatasetToggle value={dataset} onChange={setDataset} />
        </div>
      }
    />
    <ResumeBanner />
    </>
  );

  if (!profile && loading)
    return (
      <div className="space-y-6">
        {header}
        <LoadingBlock label="Analysing data quality… large files can take a few seconds" />
      </div>
    );
  if (!profile) {
    return (
      <div className="space-y-6">
        {header}
        <Alert tone="danger" title={error?.message ?? "Could not load the quality report"} action={<Button size="sm" variant="secondary" onClick={reload}>Retry</Button>}>
          {error?.hint}
        </Alert>
      </div>
    );
  }
  const s = profile.stats;
  const issues = showAll ? profile.issues : profile.issues.slice(0, ISSUE_PREVIEW);
  const health = profile.health;
  const looksEmpty = health?.looks_empty_cells ?? 0;
  const completeness = health?.real_completeness ?? s.completeness;
  const gapColumns = health ? profile.columns.filter((c) => c.missing > 0 || (c.looks_empty ?? 0) > 0).length : s.columns_with_missing;

  return (
    <div className={cn("space-y-6", loading && "opacity-70 transition-opacity")} aria-busy={loading}>
      {header}

      {dataset === "current" && info?.file.warnings.length ? (
        <Alert tone="info" title="Import notes">
          <ul className="list-disc space-y-0.5 pl-4">
            {info.file.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Alert>
      ) : null}

      {health && (
        health.needs_cleaning ? (
          <Alert
            tone="warning"
            title={`This data needs cleaning: ${pluralize(health.issues, "problem")}${health.columns_with_issues ? ` in ${pluralize(health.columns_with_issues, "column")}` : ""}${health.notes ? ` + ${pluralize(health.notes, "note")} to review` : ""}`}
          >
            Completeness only shows empty cells, so check the problems listed below. Quick Clean fixes the safe ones in one go.
          </Alert>
        ) : (
          <Alert tone="success" title={health.notes ? `No problems found, only ${pluralize(health.notes, "note")} to review` : "No problems found"}>
            The checks found nothing that needs fixing in this data.
          </Alert>
        )
      )}

      <section aria-label="Dataset overview" className="grid grid-cols-2 gap-4 md:grid-cols-3 2xl:grid-cols-6">
        <StatCard icon={Rows3} label="Total rows" value={formatNumber(s.rows)} />
        <StatCard icon={Columns3} label="Total columns" value={formatNumber(s.columns)} />
        <StatCard
          icon={SquareDashed}
          label="Missing cells"
          value={formatNumber(s.missing_cells + looksEmpty)}
          tone={s.missing_cells + looksEmpty ? "warning" : "success"}
          hint={looksEmpty ? `${formatNumber(s.missing_cells)} empty + ${formatNumber(looksEmpty)} "N/A"-style` : s.total_cells ? `of ${formatNumber(s.total_cells)} cells` : undefined}
        />
        <StatCard icon={Copy} label="Duplicate rows" value={formatNumber(s.duplicate_rows)} tone={s.duplicate_rows ? "warning" : "success"} hint={s.duplicate_rows ? "exact copies" : "none found"} />
        <StatCard icon={Columns3} label="Columns with gaps" value={formatNumber(gapColumns)} tone={gapColumns ? "warning" : "success"} hint="contain missing values" />
        <StatCard icon={Gauge} label="Completeness" value={formatPercent(completeness)} tone={completeness === null ? "neutral" : completeness >= 95 ? "success" : "warning"} hint={looksEmpty ? "cells filled in (N/A-style counts as empty)" : "cells filled in, not checked for errors"} />
      </section>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-start justify-between gap-3">
            <div>
              <CardTitle>Detected issues</CardTitle>
              <CardDescription>Potential problems. Nothing is changed until you apply a fix.</CardDescription>
            </div>
            <Badge tone={profile.issues.length ? "warning" : "success"} className="tabular">
              {profile.issues.length} found
            </Badge>
          </CardHeader>
          {profile.issues.length ? (
            <>
              <ul className="divide-y divide-border">
                {issues.map((issue) => (
                  <IssueRow key={issue.id} issue={issue} />
                ))}
              </ul>
              {profile.issues.length > ISSUE_PREVIEW && (
                <div className="border-t border-border px-5 py-2.5">
                  <Button variant="link" size="sm" onClick={() => setShowAll((v) => !v)} aria-expanded={showAll}>
                    {showAll ? "Show fewer issues" : `Show all ${profile.issues.length} issues`}
                  </Button>
                </div>
              )}
            </>
          ) : (
            <EmptyState icon={<CheckCircle2 />} title="No issues detected" className="py-10">
              The automatic checks found nothing to fix. You can still review the data or download it.
            </EmptyState>
          )}
        </Card>
        <QualitySummary profile={profile} applied={dataset === "current" ? applied : 0} />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Missing values by column</CardTitle>
            <CardDescription>Columns with the most empty cells (top 10).</CardDescription>
          </CardHeader>
          <CardContent>
            <MissingChart profile={profile} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Data types</CardTitle>
            <CardDescription>Inferred from the values in each column.</CardDescription>
          </CardHeader>
          <CardContent>
            <TypeSummary profile={profile} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Column completeness</CardTitle>
          <CardDescription>
            <strong className="font-medium text-slate-700">Completeness</strong> is the share of cells that are filled in ("N/A", "null" and
            space-only cells count as empty). 100% means no empty cells, not that the values are correct.{" "}
            <strong className="font-medium text-slate-700">Problems</strong> lists what is wrong with the values that are there, such as
            mixed date formats or different spellings.
          </CardDescription>
        </CardHeader>
        {profile.columns.length === 0 ? (
          <EmptyState title="No columns in this dataset" />
        ) : (
          <TableContainer label="Column completeness" maxHeight="max-h-[28rem]">
            <Table className="min-w-[640px]">
              <THead>
                <tr>
                  <TH scope="col" className="pl-5">Column</TH>
                  <TH scope="col">Type</TH>
                  <TH scope="col" className="text-right">Missing</TH>
                  <TH scope="col" className="text-right">Unique</TH>
                  <TH scope="col">Problems</TH>
                  <TH scope="col" className="w-1/4 pr-5">
                    Completeness <span className="font-normal normal-case text-muted-foreground">(cells filled in)</span>
                  </TH>
                </tr>
              </THead>
              <tbody>
                {profile.columns.map((c) => (
                  <TR key={c.name}>
                    <TD className="max-w-56 truncate pl-5 font-medium text-foreground" title={c.name}>
                      {c.name}
                    </TD>
                    <TD>
                      <TypeBadge type={c.type} />
                    </TD>
                    <TD className="tabular text-right">
                      {formatNumber(c.missing)}
                      {c.looks_empty ? <span className="block text-caption text-amber-800">+{formatNumber(c.looks_empty)} N/A-style</span> : null}
                    </TD>
                    <TD className="tabular text-right">{formatNumber(c.unique)}</TD>
                    <TD>
                      {c.issues === undefined ? null : c.issues ? (
                        <ColumnProblems count={c.issues} titles={problemTitles(profile.issues, c.name)} />
                      ) : (
                        <span className="inline-flex items-center gap-1 text-caption text-success">
                          <CheckCircle2 className="size-3.5" aria-hidden="true" /> OK
                        </span>
                      )}
                    </TD>
                    <TD className="pr-5">
                      <div className="flex items-center gap-3">
                        <Meter value={c.completeness} warn={!!c.issues} className="flex-1" />
                        <span className="tabular w-14 text-right text-caption text-slate-600">{formatPercent(c.completeness)}</span>
                      </div>
                      {!!c.issues && c.completeness !== null && c.completeness >= 99.995 && (
                        <span className="mt-0.5 block text-caption text-amber-800">Every cell is filled, but some values need fixing.</span>
                      )}
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </TableContainer>
        )}
      </Card>
    </div>
  );
}
