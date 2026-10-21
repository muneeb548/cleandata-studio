import { useEffect, useState } from "react";
import { Check, ClipboardCopy, Cloud, Eye, Lock, MessageSquare, Send, Sparkles, X } from "lucide-react";
import { ApiError, SESSION_GONE, api } from "@/api/client";
import type { AiAnswer, AiPlan, AiStatus, QuickCleanPreview } from "@/api/types";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Checkbox, FieldHint, Label, Select } from "@/components/ui/form";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { formatNumber, pluralize } from "@/lib/utils";
import { stepDetail, stepLabel } from "./Recipes";
import { Cell } from "./shared";
import { toApiError } from "./useAsync";
import { useWorkspace } from "./WorkspaceContext";

// The AI settings only change when the backend restarts, so one request per page load is enough.
let statusRequest: Promise<AiStatus | null> | null = null;

export function loadAiStatus(): Promise<AiStatus | null> {
  statusRequest ??= api.aiStatus().catch(() => {
    statusRequest = null; // try again next time
    return null;
  });
  return statusRequest;
}

/** The AI status, or null while loading / when the backend has no AI. */
export function useAiStatus(): AiStatus | null {
  const [status, setStatus] = useState<AiStatus | null>(null);
  useEffect(() => {
    let active = true;
    void loadAiStatus().then((s) => active && setStatus(s));
    return () => {
      active = false;
    };
  }, []);
  return status?.enabled ? status : null;
}

/** Example requests shown under the text box (clicking one fills it in). */
export const AI_EXAMPLES = [
  "Remove duplicate rows and clean the email addresses",
  "Trim spaces everywhere and make city names Title Case",
  "Phone numbers ko international format mein kar do",
  "Fill missing ages with the median",
];

/** Where the data goes and what is shared, always visible before a request. */
export function AiPrivacyNote({ status, shared, consent, onConsent, id }: {
  status: AiStatus;
  shared?: string;
  consent: boolean;
  onConsent: (on: boolean) => void;
  id: string;
}) {
  const Icon = status.local ? Lock : Cloud;
  return (
    <div className="space-y-2 rounded-md border border-border bg-canvas px-3 py-2.5 text-small text-slate-700">
      <p className="flex items-start gap-2">
        <Icon className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
        <span>
          <span className="font-medium text-foreground">{status.label}.</span>{" "}
          {status.local ? "Nothing leaves this computer. " : "This is sent over the internet to Anthropic. "}
          Shared: {shared ?? status.shared}
        </span>
      </p>
      {status.needs_consent && (
        <Checkbox id={id} checked={consent} onChange={(e) => onConsent(e.target.checked)} label="I agree to share this with the cloud AI" />
      )}
    </div>
  );
}

const canAsk = (status: AiStatus, consent: boolean) => status.ready && (!status.needs_consent || consent);

/** Overview page: describe the cleaning in your own words; the AI proposes steps, you preview and apply them. */
export function AskAiButton() {
  const status = useAiStatus();
  const { onSessionChanged, handleError, version } = useWorkspace();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [consent, setConsent] = useState(false);
  const [plan, setPlan] = useState<AiPlan | null>(null);
  const [skipped, setSkipped] = useState<Set<number>>(new Set());
  const [preview, setPreview] = useState<QuickCleanPreview | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<"plan" | "preview" | "apply" | null>(null);

  useEffect(() => {
    setPlan(null);
    setPreview(null);
  }, [version]);

  if (!status) return null;

  const chosen = plan ? plan.steps.filter((_, i) => !skipped.has(i)).map((s) => s.operation) : [];

  const fail = (err: unknown) => {
    const e = toApiError(err);
    if (SESSION_GONE.has(e.code)) {
      setOpen(false);
      handleError(e);
    } else setError(e);
  };

  const makePlan = async () => {
    setBusy("plan");
    setError(null);
    setPlan(null);
    setPreview(null);
    setSkipped(new Set());
    try {
      setPlan(await api.aiPlan(text.trim(), consent));
    } catch (err) {
      fail(err);
    } finally {
      setBusy(null);
    }
  };

  const toggle = (i: number, on: boolean) => {
    setSkipped((prev) => {
      const next = new Set(prev);
      if (on) next.delete(i);
      else next.add(i);
      return next;
    });
    setPreview(null);
  };

  const runPreview = async () => {
    setBusy("preview");
    setError(null);
    try {
      setPreview(await api.quickCleanPreview(chosen));
    } catch (err) {
      fail(err);
    } finally {
      setBusy(null);
    }
  };

  const apply = async () => {
    if (!preview) return;
    setBusy("apply");
    try {
      const res = await api.quickCleanApply(chosen, preview.preview_token);
      onSessionChanged(res.session);
      toast({ tone: "success", title: "AI plan applied", description: `${pluralize(res.applied, "step")} applied. Each one can be undone.` });
      setOpen(false);
      setText("");
    } catch (err) {
      setPreview(null);
      fail(err);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <Sparkles /> Ask AI
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        className="max-h-[90vh] max-w-2xl overflow-y-auto"
        title="Ask AI"
        description="Say what you want done, in any language. The AI only picks from the app's own cleaning steps; you preview everything before it is applied."
        footer={
          plan && plan.steps.length > 0 ? (
            <div className="flex w-full flex-wrap justify-end gap-2">
              <Button variant="secondary" onClick={runPreview} loading={busy === "preview"} disabled={!chosen.length || busy !== null}>
                {busy !== "preview" && <Eye />} Preview
              </Button>
              <Button onClick={apply} loading={busy === "apply"} disabled={!preview || !!preview.blocked || busy !== null}>
                {busy !== "apply" && <Check />} Apply {chosen.length ? pluralize(chosen.length, "step") : ""}
              </Button>
            </div>
          ) : undefined
        }
      >
        <div className="space-y-4">
          {!status.ready && status.problem && (
            <Alert tone="warning" title="The AI is not ready">
              {status.problem}
            </Alert>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="ai-request">What should be cleaned?</Label>
            <textarea
              id="ai-request"
              rows={3}
              value={text}
              maxLength={2000}
              onChange={(e) => setText(e.target.value)}
              className="w-full rounded-md border border-border-strong px-3 py-2 text-body focus-visible:border-primary"
              placeholder="e.g. duplicates hatao aur emails saaf karo"
            />
            <div className="flex flex-wrap gap-1.5">
              {AI_EXAMPLES.map((ex) => (
                <button key={ex} type="button" onClick={() => setText(ex)} className="rounded-full border border-border px-2.5 py-0.5 text-caption text-slate-600 hover:bg-muted">
                  {ex}
                </button>
              ))}
            </div>
          </div>
          <AiPrivacyNote status={status} consent={consent} onConsent={setConsent} id="ai-consent" />
          <Button onClick={makePlan} loading={busy === "plan"} disabled={text.trim().length < 3 || !canAsk(status, consent) || busy !== null}>
            {busy !== "plan" && <Sparkles />} {plan ? "Make a new plan" : "Make a plan"}
          </Button>
          {busy === "plan" && status.local && <FieldHint>A local AI can take a minute or two on a laptop.</FieldHint>}

          {error && (
            <Alert tone="danger" title={error.message}>
              {error.hint}
            </Alert>
          )}

          {plan && (
            <div className="space-y-3">
              {plan.reply && <p className="text-body text-slate-700">{plan.reply}</p>}
              {plan.steps.length === 0 ? (
                <Alert tone="info" title="No steps to suggest">
                  Try saying it differently, or use the cleaning steps directly.
                </Alert>
              ) : (
                <ul className="divide-y divide-border rounded-md border border-border">
                  {plan.steps.map((s, i) => (
                    <li key={i} className="px-3 py-2.5">
                      <Checkbox
                        id={`ai-step-${i}`}
                        checked={!skipped.has(i)}
                        onChange={(e) => toggle(i, e.target.checked)}
                        label={`${stepLabel(s.operation)}${stepDetail(s.operation)}`}
                        description={s.reason || undefined}
                      />
                    </li>
                  ))}
                </ul>
              )}
              {plan.rejected.length > 0 && (
                <Alert tone="warning" title={`${pluralize(plan.rejected.length, "suggestion")} left out by the safety check`}>
                  <ul className="list-disc space-y-0.5 pl-4">
                    {plan.rejected.map((r, i) => (
                      <li key={i}>
                        {r.label}: {r.reason}
                      </li>
                    ))}
                  </ul>
                </Alert>
              )}
            </div>
          )}

          {preview && (
            <Alert
              tone={preview.blocked ? "danger" : "success"}
              title={
                preview.blocked
                  ? "One step cannot be applied"
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
      </Dialog>
    </>
  );
}

/** Fills only the rows the user has not typed in yet; returns the merged edits and how many were added. */
export function mergeSuggestions(edits: Record<string, string>, suggestions: { value: string; to: string }[]) {
  const next = { ...edits };
  let added = 0;
  for (const s of suggestions) {
    if (!(next[s.value] ?? "").trim()) {
      next[s.value] = s.to;
      added += 1;
    }
  }
  return { edits: next, added };
}

/** Map values form: ask the AI to fill in the "Change to" column (Lhr, LAHORE → Lahore). */
export function AiSuggestMappings({ column, edits, onEdits }: { column: string; edits: Record<string, string>; onEdits: (edits: Record<string, string>) => void }) {
  const status = useAiStatus();
  const toast = useToast();
  const { handleError } = useWorkspace();
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!status || !column) return null;
  if (!status.sends_values) return <FieldHint>AI suggestions are off because sharing values with the AI is turned off (AI_SEND_VALUES).</FieldHint>;

  const suggest = async () => {
    setBusy(true);
    try {
      const res = await api.aiMapValues(column, consent);
      const { edits: next, added } = mergeSuggestions(edits, res.mappings);
      onEdits(next);
      toast(
        added
          ? { tone: "success", title: `${pluralize(added, "suggestion")} filled in`, description: "Check them in the table, change any you disagree with, then preview." }
          : { tone: "info", title: "No changes suggested", description: "The AI found no values that mean the same thing." },
      );
    } catch (err) {
      handleError(err, "AI suggestions failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <AiPrivacyNote status={status} shared={`the most common different values of "${column}" and how often each appears.`} consent={consent} onConsent={setConsent} id="ai-map-consent" />
      <Button variant="secondary" size="sm" onClick={suggest} loading={busy} disabled={!canAsk(status, consent)}>
        {!busy && <Sparkles />} Suggest with AI
      </Button>
      {!status.ready && status.problem && <FieldHint>{status.problem}</FieldHint>}
    </div>
  );
}

const LANGUAGES = ["English", "Urdu", "Roman Urdu", "Arabic", "Spanish", "French", "German", "Portuguese", "Hindi"];

/** Download page: a plain-language report of the cleaning, written by the AI. */
export function AiSummaryCard() {
  const status = useAiStatus();
  const toast = useToast();
  const { version, info } = useWorkspace();
  const [language, setLanguage] = useState("English");
  const [consent, setConsent] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => setText(null), [version]);
  if (!status) return null;

  const write = async () => {
    setBusy(true);
    setError(null);
    try {
      setText((await api.aiSummary(language, consent)).summary);
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      toast({ tone: "success", title: "Copied" });
    } catch {
      toast({ tone: "info", title: "Copy not available", description: "Select the text and copy it manually." });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="size-4 text-primary" aria-hidden="true" /> AI summary <Badge tone="accent">Optional</Badge>
        </CardTitle>
        <CardDescription>A short, friendly explanation of what was wrong and what was fixed, in your client's language. Check it before you send it.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1.5">
            <Label htmlFor="ai-lang">Language</Label>
            <Select id="ai-lang" value={language} onChange={(e) => setLanguage(e.target.value)} className="w-44">
              {LANGUAGES.map((l) => (
                <option key={l}>{l}</option>
              ))}
            </Select>
          </div>
          <Button onClick={write} loading={busy} disabled={!canAsk(status, consent) || !info?.history.length}>
            {!busy && <Sparkles />} Write summary
          </Button>
        </div>
        {!info?.history.length && <FieldHint>Apply at least one cleaning step first.</FieldHint>}
        {status.local && language !== "English" && (
          <FieldHint>The local AI writes best in English; other languages can contain mistakes, so read the summary carefully before sending it.</FieldHint>
        )}
        <AiPrivacyNote status={status} shared="the change report (row and column counts and the list of applied steps)." consent={consent} onConsent={setConsent} id="ai-sum-consent" />
        {error && (
          <Alert tone="danger" title={error.message}>
            {error.hint}
          </Alert>
        )}
        {text && (
          <>
            <pre className="scroll-thin max-h-80 overflow-auto rounded-md border border-border bg-canvas p-3 font-sans text-small whitespace-pre-wrap">{text}</pre>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={copy}>
                <ClipboardCopy /> Copy
              </Button>
              <Button variant="ghost" onClick={() => setText(null)}>
                <X /> Clear
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** Example questions shown in the chat (clicking one asks it). */
export const QUESTION_EXAMPLES = [
  "Which city has the most rows?",
  "How many emails are missing?",
  "Har country ka total amount kitna hai?",
];

type ChatEntry = { question: string; result?: AiAnswer; error?: ApiError };

/** Overview page: ask questions about the data. The AI writes a query plan, the app calculates the answer. */
export function ChatWithDataButton() {
  const status = useAiStatus();
  const { handleError, version } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [consent, setConsent] = useState(false);
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => setEntries([]), [version]);
  if (!status) return null;

  const ask = async (question: string) => {
    const q = question.trim();
    if (q.length < 3 || busy) return;
    setBusy(true);
    setText("");
    setEntries((prev) => [...prev, { question: q }]);
    let entry: ChatEntry;
    try {
      entry = { question: q, result: await api.aiAsk(q, consent) };
    } catch (err) {
      const e = toApiError(err);
      if (SESSION_GONE.has(e.code)) {
        setOpen(false);
        handleError(e);
        setBusy(false);
        return;
      }
      entry = { question: q, error: e };
    }
    setEntries((prev) => [...prev.slice(0, -1), entry]);
    setBusy(false);
  };

  const ready = canAsk(status, consent);

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <MessageSquare /> Ask a question
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        className="max-h-[90vh] max-w-3xl overflow-y-auto"
        title="Ask about your data"
        description="Ask in any language. The AI only decides what to calculate; the app does the calculation on your data, so every number is real. Nothing is changed."
      >
        <div className="space-y-4">
          {!status.ready && status.problem && (
            <Alert tone="warning" title="The AI is not ready">
              {status.problem}
            </Alert>
          )}
          <AiPrivacyNote status={status} consent={consent} onConsent={setConsent} id="ai-ask-consent" />

          {entries.length === 0 && (
            <div className="flex flex-wrap gap-1.5">
              {QUESTION_EXAMPLES.map((ex) => (
                <button key={ex} type="button" disabled={!ready} onClick={() => void ask(ex)} className="rounded-full border border-border px-2.5 py-0.5 text-caption text-slate-600 hover:bg-muted disabled:opacity-50">
                  {ex}
                </button>
              ))}
            </div>
          )}

          <ol className="space-y-4" aria-live="polite">
            {entries.map((e, i) => (
              <li key={i} className="space-y-2">
                <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-primary-soft px-3 py-2 text-body text-blue-900">{e.question}</p>
                {!e.result && !e.error && <FieldHint>Thinking… {status.local ? "a local AI can take a minute or two." : ""}</FieldHint>}
                {e.error && (
                  <Alert tone="danger" title={e.error.message}>
                    {e.error.hint}
                  </Alert>
                )}
                {e.result && <AnswerCard result={e.result} />}
              </li>
            ))}
          </ol>

          <form
            className="flex items-end gap-2"
            onSubmit={(ev) => {
              ev.preventDefault();
              void ask(text);
            }}
          >
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="ai-question">Your question</Label>
              <input
                id="ai-question"
                value={text}
                maxLength={1000}
                onChange={(ev) => setText(ev.target.value)}
                placeholder="e.g. kis city mein sab se zyada customers hain?"
                className="h-9 w-full rounded-md border border-border-strong px-3 text-body focus-visible:border-primary"
              />
            </div>
            <Button type="submit" loading={busy} disabled={text.trim().length < 3 || !ready}>
              {!busy && <Send />} Ask
            </Button>
          </form>
        </div>
      </Dialog>
    </>
  );
}

function AnswerCard({ result }: { result: AiAnswer }) {
  if (!result.possible) {
    return (
      <Alert tone="info" title="This table cannot answer that">
        {result.answer}
      </Alert>
    );
  }
  const single = result.rows.length === 1 && result.columns.length === 1;
  return (
    <div className="space-y-2 rounded-lg border border-border p-3">
      <p className="text-body font-medium text-foreground">{result.answer}</p>
      {!single && result.rows.length > 0 && (
        <div className="scroll-thin max-h-72 overflow-auto rounded-md border border-border">
          <Table>
            <THead>
              <tr>
                {result.columns.map((c, i) => (
                  <TH key={c + i} scope="col" className={i === result.columns.length - 1 ? "pr-3 text-right" : "pl-3"}>
                    {c}
                  </TH>
                ))}
              </tr>
            </THead>
            <tbody>
              {result.rows.map((row, r) => (
                <TR key={r}>
                  {row.map((v, i) => (
                    <TD key={i} className={i === row.length - 1 ? "tabular pr-3 text-right" : "pl-3"}>
                      {typeof v === "number" ? formatNumber(v) : <Cell value={v} />}
                    </TD>
                  ))}
                </TR>
              ))}
            </tbody>
          </Table>
        </div>
      )}
      {result.notes.map((n) => (
        <p key={n} className="text-caption text-amber-800">
          {n}
        </p>
      ))}
      <details className="text-caption text-muted-foreground">
        <summary className="cursor-pointer">How this was calculated ({formatNumber(result.rows_matched)} rows used)</summary>
        <ol className="mt-1 list-decimal space-y-0.5 pl-5">
          {result.steps.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
      </details>
    </div>
  );
}
