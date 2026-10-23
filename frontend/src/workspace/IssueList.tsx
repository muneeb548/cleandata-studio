import { useState } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Flag, Info, Undo2, Wrench, type LucideIcon } from "lucide-react";
import { api } from "@/api/client";
import type { Issue, IssueAction, Profile, ReviewedIssue, Severity } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { EmptyState } from "@/components/ui/misc";
import { useToast } from "@/components/ui/toast";
import { cn, pluralize } from "@/lib/utils";
import { useWorkspace } from "./WorkspaceContext";

const SEVERITY: Record<Severity, { label: string; tone: "danger" | "warning" | "neutral" | "primary"; icon: LucideIcon; color: string }> = {
  high: { label: "High", tone: "danger", icon: AlertCircle, color: "text-danger" },
  medium: { label: "Medium", tone: "warning", icon: AlertTriangle, color: "text-warning" },
  low: { label: "Low", tone: "neutral", icon: Info, color: "text-slate-500" },
  info: { label: "Review", tone: "primary", icon: Info, color: "text-primary" },
};

export const GROUPS: { action: IssueAction; title: string; hint: string; icon: LucideIcon; color: string }[] = [
  { action: "fix", title: "Tool can fix", hint: "The right value is certain. Use Fix, or Quick Clean for all safe fixes.", icon: Wrench, color: "text-primary" },
  { action: "client", title: "Needs your client", hint: "Fixing these would need a guess. Flag the rows and ask your client, or mark as reviewed.", icon: Flag, color: "text-warning" },
  { action: "info", title: "Just information", hint: "Nothing is wrong. Mark as reviewed to note it in the change report.", icon: Info, color: "text-slate-500" },
];

const PREVIEW = 8;

type Props = { profile: Profile; editable: boolean; onChanged: () => void };

/** Overview → Detected issues, grouped by what to do about them. */
export function IssueList({ profile, editable, onChanged }: Props) {
  const [showAll, setShowAll] = useState(false);
  const issues = profile.issues;
  const reviewed = profile.reviewed ?? [];
  const triage = profile.triage;
  let shown = 0;
  const limit = showAll ? Infinity : PREVIEW;

  if (!issues.length && !reviewed.length) {
    return (
      <EmptyState icon={<CheckCircle2 />} title="No issues detected" className="py-10">
        The automatic checks found nothing to fix. You can still review the data or download it.
      </EmptyState>
    );
  }

  return (
    <div>
      {triage && <Verdict triage={triage} />}
      {GROUPS.map((g) => {
        const items = issues.filter((i) => (i.action ?? "fix") === g.action);
        if (!items.length) return null;
        const visible = items.slice(0, Math.max(0, limit - shown));
        shown += visible.length;
        if (!visible.length) return null;
        return (
          <section key={g.action} aria-labelledby={`issues-${g.action}`} className="border-t border-border">
            <header className="flex items-start gap-2 bg-canvas px-5 py-2.5">
              <g.icon className={cn("mt-0.5 size-4 shrink-0", g.color)} aria-hidden="true" />
              <div className="min-w-0">
                <h3 id={`issues-${g.action}`} className="text-small font-semibold text-foreground">
                  {g.title} <span className="tabular font-normal text-muted-foreground">({items.length})</span>
                </h3>
                <p className="text-caption text-muted-foreground">{g.hint}</p>
              </div>
            </header>
            <ul className="divide-y divide-border">
              {visible.map((issue) => (
                <IssueRow key={issue.id} issue={issue} editable={editable} onChanged={onChanged} />
              ))}
            </ul>
          </section>
        );
      })}
      {issues.length > PREVIEW && (
        <div className="border-t border-border px-5 py-2.5">
          <Button variant="link" size="sm" onClick={() => setShowAll((v) => !v)} aria-expanded={showAll}>
            {showAll ? "Show fewer issues" : `Show all ${issues.length} issues`}
          </Button>
        </div>
      )}
      {reviewed.length > 0 && <ReviewedList items={reviewed} editable={editable} onChanged={onChanged} />}
    </div>
  );
}

function Verdict({ triage }: { triage: NonNullable<Profile["triage"]> }) {
  let tone: "success" | "warning" | "info" = "info";
  let text: string;
  if (triage.fix > 0) {
    text = `${pluralize(triage.fix, "issue")} the tool can fix.`;
    if (triage.client) text += ` ${pluralize(triage.client, "item")} for your client after that.`;
  } else if (triage.client_open > 0) {
    tone = "warning";
    text = `Nothing left that the tool can fix. ${pluralize(triage.client_open, "item")} ${triage.client_open === 1 ? "needs" : "need"} your client: flag ${triage.client_open === 1 ? "it" : "them"} or mark as reviewed.`;
  } else {
    tone = "success";
    text = "Cleaning is complete: nothing left to fix, and everything for your client is flagged or reviewed.";
  }
  return (
    <p
      className={cn(
        "flex items-start gap-2 border-t border-border px-5 py-2.5 text-small font-medium",
        tone === "success" && "bg-success-soft text-green-800",
        tone === "warning" && "bg-warning-soft text-amber-900",
        tone === "info" && "text-slate-700",
      )}
      aria-live="polite"
    >
      {tone === "success" ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> : <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
      {text}
    </p>
  );
}

function IssueRow({ issue, editable, onChanged }: { issue: Issue; editable: boolean; onChanged: () => void }) {
  const { openOperation, handleError } = useWorkspace();
  const toast = useToast();
  const sev = SEVERITY[issue.severity];
  const [reviewing, setReviewing] = useState(false);
  const [reason, setReason] = useState(issue.suggested_reason ?? "");
  const [busy, setBusy] = useState(false);
  const action = issue.action ?? "fix";
  const op = issue.suggested_operation;

  const save = async () => {
    setBusy(true);
    try {
      await api.reviewIssue(issue.id, reason);
      toast({ tone: "success", title: "Marked as reviewed", description: "It is listed in the change report under “Checked and left as they are”." });
      setReviewing(false);
      onChanged();
    } catch (err) {
      handleError(err, "Could not mark it as reviewed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="px-5 py-3">
      <div className="flex items-start gap-3">
        <sev.icon className={cn("mt-0.5 size-4 shrink-0", sev.color)} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 text-small font-medium text-foreground">
            <span className="break-words">{issue.title}</span>
            <Badge tone={sev.tone}>{sev.label}</Badge>
            {issue.flagged_in && (
              <Badge tone="success">
                <CheckCircle2 className="size-3" aria-hidden="true" /> Flagged in “{issue.flagged_in}”
              </Badge>
            )}
          </p>
          <p className="mt-0.5 text-caption text-muted-foreground">{issue.description}</p>
        </div>
        {editable && (
          <div className="flex shrink-0 flex-wrap justify-end gap-2">
            {op && !(op === "flag_rows" && issue.flagged_in) && (
              <Button variant="secondary" size="sm" onClick={() => openOperation(op, issue.column, issue.id, issue.example)}>
                {op === "flag_rows" ? <Flag /> : <Wrench />} {op === "outliers" ? "Review" : op === "flag_rows" ? "Flag" : "Fix"}
              </Button>
            )}
            {action !== "fix" && !reviewing && (
              <Button variant="ghost" size="sm" onClick={() => setReviewing(true)}>
                <CheckCircle2 /> Mark as reviewed
              </Button>
            )}
          </div>
        )}
      </div>
      {reviewing && (
        <form
          className="mt-3 ml-7 flex flex-col gap-2 sm:flex-row sm:items-center"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <label htmlFor={`why-${issue.id}`} className="shrink-0 text-caption font-medium text-slate-700">
            Why is this fine?
          </label>
          <Input id={`why-${issue.id}`} value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Not every customer is a loyalty member." className="min-w-0 flex-1" autoFocus />
          <div className="flex gap-2">
            <Button size="sm" type="submit" loading={busy} disabled={!reason.trim() || busy}>
              Save
            </Button>
            <Button size="sm" variant="ghost" type="button" onClick={() => setReviewing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </li>
  );
}

function ReviewedList({ items, editable, onChanged }: { items: ReviewedIssue[]; editable: boolean; onChanged: () => void }) {
  const { handleError } = useWorkspace();
  const undo = async (id: string) => {
    try {
      await api.unreviewIssue(id);
      onChanged();
    } catch (err) {
      handleError(err, "Could not undo the review");
    }
  };
  return (
    <section aria-labelledby="issues-reviewed" className="border-t border-border">
      <header className="flex items-start gap-2 bg-canvas px-5 py-2.5">
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
        <div>
          <h3 id="issues-reviewed" className="text-small font-semibold text-foreground">
            Reviewed <span className="tabular font-normal text-muted-foreground">({items.length})</span>
          </h3>
          <p className="text-caption text-muted-foreground">Checked and left as they are. Listed in the change report with your reason.</p>
        </div>
      </header>
      <ul className="divide-y divide-border">
        {items.map((r) => (
          <li key={r.id} className="flex items-start gap-3 px-5 py-2.5">
            <div className="min-w-0 flex-1">
              <p className={cn("text-small", r.still_open ? "text-foreground" : "text-muted-foreground line-through")}>{r.title}</p>
              <p className="text-caption text-muted-foreground">
                {r.reason}
                {!r.still_open && " · no longer detected"}
              </p>
            </div>
            {editable && (
              <Button variant="ghost" size="sm" onClick={() => void undo(r.id)} aria-label={`Undo review: ${r.title}`}>
                <Undo2 /> Undo
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
