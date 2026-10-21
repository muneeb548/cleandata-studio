import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Download,
  FilePlus,
  FileSpreadsheet,
  GitCompareArrows,
  LayoutDashboard,
  RotateCcw,
  ShieldCheck,
  Table2,
  Undo2,
  WandSparkles,
  type LucideIcon,
} from "lucide-react";
import { Logo } from "@/components/layout/Logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { LoadingBlock } from "@/components/ui/misc";
import { Tooltip } from "@/components/ui/tooltip";
import { Link } from "@/lib/router";
import { usePageMeta } from "@/lib/seo";
import { cn, formatBytes, formatNumber, pluralize } from "@/lib/utils";
import { CleanPanel } from "@/workspace/CleanPanel";
import { ComparePanel } from "@/workspace/ComparePanel";
import { DataPanel } from "@/workspace/DataPanel";
import { DeleteDataButton } from "@/workspace/DeleteDataButton";
import { ExportPanel } from "@/workspace/ExportPanel";
import { OverviewPanel } from "@/workspace/OverviewPanel";
import { UploadPanel } from "@/workspace/UploadPanel";
import { WorkspaceProvider, useWorkspace, type Tab } from "@/workspace/WorkspaceContext";

const NAV: { id: Tab; label: string; short: string; hint: string; icon: LucideIcon }[] = [
  { id: "overview", label: "Overview", short: "Overview", hint: "Quality report", icon: LayoutDashboard },
  { id: "data", label: "Data preview", short: "Data", hint: "Browse and search", icon: Table2 },
  { id: "clean", label: "Clean data", short: "Clean", hint: "Preview and apply", icon: WandSparkles },
  { id: "compare", label: "Compare", short: "Compare", hint: "Before and after", icon: GitCompareArrows },
  { id: "export", label: "Download", short: "Download", hint: "CSV or Excel", icon: Download },
];

function TopBar() {
  const { status, info, undo, reset, startOver, pending, setTab } = useWorkspace();
  const [confirm, setConfirm] = useState<"reset" | "replace" | null>(null);
  const ready = status === "ready" && info;
  const applied = info?.history.length ?? 0;
  const last = info?.history[info.history.length - 1];

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background">
      <div className="flex h-topbar items-center gap-3 px-4 sm:px-6">
        <Logo />
        {ready && (
          <div className="ml-1 hidden min-w-0 items-center gap-2.5 border-l border-border pl-4 md:flex">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary">
              <FileSpreadsheet className="size-4" aria-hidden="true" />
            </span>
            <div className="min-w-0 leading-tight">
              <p className="truncate text-small font-semibold text-foreground" title={info.file.name}>
                {info.file.name}
              </p>
              <p className="truncate text-caption text-muted-foreground">
                {info.file.format_label}
                {info.file.sheet ? ` · ${info.file.sheet}` : ""} · {formatBytes(info.file.size)} ·{" "}
                <span className="tabular">
                  {formatNumber(info.current_shape.rows)} rows × {formatNumber(info.current_shape.columns)} columns
                </span>
              </p>
            </div>
          </div>
        )}
        <div className="ml-auto flex items-center gap-1">
          {ready ? (
            <>
              <Tooltip content={info.can_undo ? `Undo “${last?.label}”` : applied ? "Older steps were removed from memory" : "Nothing to undo yet"} side="bottom" align="end">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void undo()}
                  loading={pending === "undo"}
                  disabled={!info.can_undo || pending !== null}
                  aria-label="Undo last operation"
                >
                  {pending !== "undo" && <Undo2 />}
                  <span className="hidden xl:inline">Undo</span>
                </Button>
              </Tooltip>
              <Tooltip content={applied ? "Restore the original upload" : "No changes to reset"} side="bottom" align="end">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfirm("reset")}
                  loading={pending === "reset"}
                  disabled={applied === 0 || pending !== null}
                  aria-label="Reset to original data"
                >
                  {pending !== "reset" && <RotateCcw />}
                  <span className="hidden xl:inline">Reset</span>
                </Button>
              </Tooltip>
              <span className="mx-1 hidden h-5 w-px bg-border sm:block" aria-hidden="true" />
              <Tooltip content="Upload a different file" side="bottom" align="end">
                <Button variant="secondary" size="sm" onClick={() => setConfirm("replace")} disabled={pending !== null} aria-label="Replace file">
                  <FilePlus />
                  <span className="hidden sm:inline">Replace file</span>
                </Button>
              </Tooltip>
              <Button size="sm" onClick={() => setTab("export")} className="ml-1" aria-label="Download cleaned data">
                <Download />
                <span className="hidden sm:inline">Download</span>
              </Button>
            </>
          ) : (
            <Link href="/" className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-small text-slate-600 hover:bg-muted hover:text-foreground">
              <ArrowLeft className="size-4" aria-hidden="true" /> Back to website
            </Link>
          )}
        </div>
      </div>

      <Dialog
        open={confirm === "reset"}
        onClose={() => setConfirm(null)}
        title="Reset to the original data?"
        description={`This removes ${pluralize(applied, "applied operation")} and restores the dataset exactly as uploaded. This cannot be undone.`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                setConfirm(null);
                void reset();
              }}
            >
              Reset data
            </Button>
          </>
        }
      />
      <Dialog
        open={confirm === "replace"}
        onClose={() => setConfirm(null)}
        title="Replace the current file?"
        description="The current dataset and its cleaning history will be deleted from the server. Download your cleaned file first if you need it."
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setConfirm(null);
                setTab("export");
              }}
            >
              Download first
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                setConfirm(null);
                void startOver();
              }}
            >
              Delete and upload new file
            </Button>
          </>
        }
      />
    </header>
  );
}

function Sidebar() {
  const { tab, setTab, info, config } = useWorkspace();
  if (!info) return null;
  const applied = info.history.length;
  const rowsChanged = info.current_shape.rows !== info.original_shape.rows;
  return (
    <aside className="sticky top-topbar hidden h-[calc(100dvh-var(--spacing-topbar))] w-sidebar shrink-0 flex-col border-r border-border bg-background lg:flex">
      <nav aria-label="Workspace" className="flex-1 overflow-y-auto px-3 py-4">
        <p className="eyebrow px-2 pb-2">Workflow</p>
        <ul className="space-y-0.5">
          {NAV.map((item, i) => {
            const active = tab === item.id;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => setTab(item.id)}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "group flex w-full items-center gap-3 rounded-md px-2 py-2 text-left transition-colors",
                    active ? "bg-primary-soft" : "hover:bg-muted",
                  )}
                >
                  <span
                    className={cn(
                      "flex size-8 shrink-0 items-center justify-center rounded-md border",
                      active ? "border-blue-200 bg-background text-primary" : "border-border bg-background text-slate-500 group-hover:text-slate-700",
                    )}
                  >
                    <item.icon className="size-4" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className={cn("block text-small font-medium", active ? "text-blue-900" : "text-foreground")}>
                      <span className="tabular mr-1 text-slate-600">{i + 1}.</span>
                      {item.label}
                    </span>
                    <span className="block text-caption text-muted-foreground">{item.hint}</span>
                  </span>
                  {item.id === "clean" && applied > 0 && (
                    <Badge tone="success" className="tabular">
                      {applied}
                    </Badge>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="space-y-3 border-t border-border p-4">
        <p className="eyebrow">Dataset</p>
        <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-small">
          <div>
            <dt className="text-caption text-muted-foreground">Rows</dt>
            <dd className="tabular font-medium">
              {formatNumber(info.current_shape.rows)}
              {rowsChanged && <span className="block text-caption font-normal text-muted-foreground">of {formatNumber(info.original_shape.rows)}</span>}
            </dd>
          </div>
          <div>
            <dt className="text-caption text-muted-foreground">Columns</dt>
            <dd className="tabular font-medium">{formatNumber(info.current_shape.columns)}</dd>
          </div>
          <div>
            <dt className="text-caption text-muted-foreground">Format</dt>
            <dd className="font-medium">{info.file.format.toUpperCase()}</dd>
          </div>
          <div>
            <dt className="text-caption text-muted-foreground">Changes</dt>
            <dd className="tabular font-medium">{applied}</dd>
          </div>
        </dl>
        <p className="flex gap-2 text-caption text-muted-foreground">
          <ShieldCheck className="mt-px size-3.5 shrink-0 text-slate-500" aria-hidden="true" />
          <span>
            Deleted after {config?.session_ttl_minutes ?? 30} min of inactivity.{" "}
            <Link href="/privacy" className="text-primary hover:underline">
              Privacy
            </Link>
          </span>
        </p>
        <DeleteDataButton className="w-full" />
      </div>
    </aside>
  );
}

/** Tablet and phone navigation (the sidebar is hidden below 1024px). */
function MobileNav() {
  const { tab, setTab, info } = useWorkspace();
  return (
    <nav aria-label="Workspace" className="border-b border-border bg-background lg:hidden">
      {info && (
        <p className="flex items-center gap-2 border-b border-border px-4 py-2 text-caption text-muted-foreground md:hidden">
          <FileSpreadsheet className="size-3.5 shrink-0 text-primary" aria-hidden="true" />
          <span className="truncate font-medium text-foreground">{info.file.name}</span>
          <span className="tabular ml-auto shrink-0">
            {formatNumber(info.current_shape.rows)} × {formatNumber(info.current_shape.columns)}
          </span>
        </p>
      )}
      <ul className="scroll-thin flex gap-1 overflow-x-auto px-3 sm:px-5">
        {NAV.map((item) => {
          const active = tab === item.id;
          return (
            <li key={item.id} className="shrink-0">
              <button
                type="button"
                onClick={() => setTab(item.id)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2 border-b-2 px-2.5 py-3 text-small font-medium transition-colors",
                  active ? "border-primary text-primary" : "border-transparent text-slate-600 hover:text-foreground",
                )}
              >
                <item.icon className="size-4" aria-hidden="true" />
                <span className="sm:hidden">{item.short}</span>
                <span className="hidden sm:inline">{item.label}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function WorkspaceBody() {
  const { status, tab } = useWorkspace();
 useEffect(() => {
  window.scrollTo({ top: 0 });
}, [tab]);

  if (status === "loading") return <LoadingBlock label="Restoring your session…" className="min-h-[60vh]" />;
  if (status === "empty") {
    return (
      <div className="px-4 sm:px-6">
        <UploadPanel />
      </div>
    );
  }
  return (
    <div className="flex">
      <Sidebar />
      <div className="min-w-0 flex-1">
        <MobileNav />
        <div id="workspace-panel" className="mx-auto w-full max-w-[80rem] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {tab === "overview" && <OverviewPanel />}
          {tab === "data" && <DataPanel />}
          {tab === "clean" && <CleanPanel />}
          {tab === "compare" && <ComparePanel />}
          {tab === "export" && <ExportPanel />}
        </div>
      </div>
    </div>
  );
}

function UploadFooter() {
  const { status, config } = useWorkspace();
  if (status === "ready") return null;
  return (
    <footer className="border-t border-border bg-background px-4 py-3 text-center text-caption text-muted-foreground sm:px-6">
      Data is processed on the server and deleted after {config?.session_ttl_minutes ?? 30} minutes of inactivity.{" "}
      <Link href="/privacy" className="text-primary hover:underline">
        Privacy
      </Link>
    </footer>
  );
}

export function WorkspacePage() {
  usePageMeta({
    title: "Workspace — CleanData Studio",
    description: "Upload, inspect and clean a CSV, Excel or JSON file.",
    path: "/app",
    index: false,
  });
  return (
    <WorkspaceProvider>
      <div className="flex min-h-dvh flex-col overflow-x-clip bg-canvas">
        <TopBar />
        <main className="flex-1">
          <WorkspaceBody />
        </main>
        <UploadFooter />
      </div>
    </WorkspaceProvider>
  );
}
