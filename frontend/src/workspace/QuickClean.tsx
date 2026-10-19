import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, ClipboardCopy, Download, Eye, FileText, Zap } from "lucide-react";
import { api } from "@/api/client";
import type { QuickCleanPlan, QuickCleanPreview } from "@/api/types";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/form";
import { LoadingBlock } from "@/components/ui/misc";
import { useToast } from "@/components/ui/toast";
import { formatNumber, pluralize } from "@/lib/utils";
import { useAsync } from "./useAsync";
import { useWorkspace } from "./WorkspaceContext";

/** One button that proposes every safe fix for the working data, previews them together and applies them. */
export function QuickCleanButton() {
  const { onSessionChanged, handleError, version } = useWorkspace();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [plan, setPlan] = useState<QuickCleanPlan | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<QuickCleanPreview | null>(null);
  const [busy, setBusy] = useState<"plan" | "preview" | "apply" | null>(null);

  useEffect(() => {
    setPlan(null);
    setPreview(null);
  }, [version]);

  const load = async () => {
    setOpen(true);
    if (plan) return;
    setBusy("plan");
    try {
      const p = await api.quickCleanPlan();
      setPlan(p);
      setSelected(new Set(p.steps.filter((s) => s.selected).map((s) => s.id)));
    } catch (err) {
      setOpen(false);
      handleError(err, "Could not prepare Quick Clean");
    } finally {
      setBusy(null);
    }
  };

  const chosen = useMemo(() => (plan ? plan.steps.filter((s) => selected.has(s.id)) : []), [plan, selected]);

  const toggle = (id: string, on: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
    setPreview(null);
  };

  const runPreview = async () => {
    setBusy("preview");
    try {
      setPreview(await api.quickCleanPreview(chosen.map((s) => s.operation)));
    } catch (err) {
      handleError(err, "Preview failed");
    } finally {
      setBusy(null);
    }
  };

  const apply = async () => {
    if (!preview) return;
    setBusy("apply");
    try {
      const res = await api.quickCleanApply(chosen.map((s) => s.operation), preview.preview_token);
      onSessionChanged(res.session);
      toast({ tone: "success", title: "Quick Clean applied", description: `${pluralize(res.applied, "fix", "fixes")} applied. Each one can be undone.` });
      setOpen(false);
    } catch (err) {
      setPreview(null);
      handleError(err, "Quick Clean could not be applied");
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <Button onClick={load} loading={busy === "plan"}>
        {busy !== "plan" && <Zap />} Quick Clean
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        className="max-h-[90vh] max-w-2xl overflow-y-auto"
        title="Quick Clean"
        description="Safe fixes that keep the meaning of your data. Untick anything you don't want, preview, then apply."
        footer={
          plan && plan.steps.length > 0 ? (
            <div className="flex w-full flex-wrap justify-end gap-2">
              <Button variant="secondary" onClick={runPreview} loading={busy === "preview"} disabled={!chosen.length || busy !== null}>
                {busy !== "preview" && <Eye />} Preview
              </Button>
              <Button onClick={apply} loading={busy === "apply"} disabled={!preview || !!preview.blocked || busy !== null}>
                {busy !== "apply" && <Check />} Apply {chosen.length ? pluralize(chosen.length, "fix", "fixes") : ""}
              </Button>
            </div>
          ) : undefined
        }
      >
        {!plan ? (
          <LoadingBlock label="Looking for safe fixes…" />
        ) : (
          <div className="space-y-4">
            {plan.steps.length === 0 ? (
              <Alert tone="success" title="Nothing to fix automatically">
                The data has no problems that can be fixed safely without a decision.
              </Alert>
            ) : (
              <ul className="divide-y divide-border rounded-md border border-border">
                {plan.steps.map((step) => (
                  <li key={step.id} className="px-3 py-2.5">
                    <Checkbox
                      id={`qc-${step.id}`}
                      checked={selected.has(step.id)}
                      onChange={(e) => toggle(step.id, e.target.checked)}
                      label={step.title}
                      description={step.summary}
                    />
                    {step.note && (
                      <p className="mt-1.5 ml-6.5 flex gap-1.5 text-caption text-amber-800">
                        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" /> {step.note}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {plan.needs_decision.length > 0 && (
              <Alert tone="info" title="Not changed: needs your decision">
                <ul className="list-disc space-y-0.5 pl-4">
                  {plan.needs_decision.map((d) => (
                    <li key={d}>{d}</li>
                  ))}
                </ul>
              </Alert>
            )}
            {preview && (
              <Alert
                tone={preview.blocked ? "danger" : "success"}
                title={
                  preview.blocked
                    ? "One fix cannot be applied"
                    : `If applied: rows ${formatNumber(preview.rows_before)} → ${formatNumber(preview.rows_after)}, columns ${formatNumber(preview.columns_before)} → ${formatNumber(preview.columns_after)}, ${formatNumber(preview.cells_changed)} cells changed`
                }
              >
                {preview.blocked ?? (
                  <ul className="list-disc space-y-0.5 pl-4">
                    {preview.steps.map((s, i) => (
                      <li key={i}>{s.summary}</li>
                    ))}
                  </ul>
                )}
              </Alert>
            )}
          </div>
        )}
      </Dialog>
    </>
  );
}

/** What was done to the file, ready to send to the client. */
export function ChangeReportCard() {
  const { version, info } = useWorkspace();
  const toast = useToast();
  const { data: report, error, reload } = useAsync(() => api.report(), [version], version);

  const copy = async () => {
    if (!report) return;
    try {
      await navigator.clipboard.writeText(report.message);
      toast({ tone: "success", title: "Copied", description: "Paste it into your message to the client." });
    } catch {
      toast({ tone: "info", title: "Copy not available", description: "Select the text and copy it manually." });
    }
  };

  const download = () => {
    if (!report) return;
    const stem = (info?.file.name ?? "data").replace(/\.[^.]+$/, "");
    const url = URL.createObjectURL(new Blob([report.message], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${stem}_cleaning_report.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="size-4 text-primary" aria-hidden="true" /> Change report
        </CardTitle>
        <CardDescription>A summary of everything that was changed, written for your client.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {error ? (
          <Alert tone="danger" title={error.message} action={<Button size="sm" variant="secondary" onClick={reload}>Retry</Button>}>
            {error.hint}
          </Alert>
        ) : !report ? (
          <LoadingBlock />
        ) : (
          <>
            <pre className="scroll-thin max-h-80 overflow-auto rounded-md border border-border bg-canvas p-3 font-sans text-small whitespace-pre-wrap">
              {report.message}
            </pre>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={copy}>
                <ClipboardCopy /> Copy message
              </Button>
              <Button variant="secondary" onClick={download}>
                <Download /> Download report (.txt)
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
