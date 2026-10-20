import { useRef, useState } from "react";
import { BookOpen, Check, Download, Eye, FileUp } from "lucide-react";
import { ApiError, SESSION_GONE, api } from "@/api/client";
import type { Operation, QuickCleanPreview, Recipe } from "@/api/types";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { formatNumber, pluralize } from "@/lib/utils";
import { CHOICES } from "./operationForms";
import { toApiError } from "./useAsync";
import { useWorkspace } from "./WorkspaceContext";

export const stepLabel = (op: Operation) => CHOICES.find((c) => c.id === op.type)?.label ?? op.type;

export function stepDetail(op: Operation): string {
  const cols = "columns" in op && Array.isArray(op.columns) && op.columns.length ? ` · ${op.columns.join(", ")}` : "";
  const col = "column" in op && typeof op.column === "string" ? ` · ${op.column}` : "";
  return cols || col;
}

/** Reads a recipe file and checks that it really is one, without trusting its contents. */
export function parseRecipe(text: string): Recipe {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error("This file is not valid JSON.");
  }
  const r = data as Partial<Recipe> | null;
  if (!r || r.kind !== "cleaning-recipe" || !Array.isArray(r.steps)) throw new Error("This is not a CleanData Studio recipe file.");
  if (!r.steps.length) throw new Error("The recipe has no steps.");
  if (!r.steps.every((s) => s && typeof s === "object" && typeof (s as { type?: unknown }).type === "string"))
    throw new Error("The recipe contains an unreadable step.");
  return { ...r, name: typeof r.name === "string" ? r.name : "Recipe" } as Recipe;
}

/** Download page: save the applied steps as a .json recipe. */
export function RecipeCard() {
  const { info, handleError } = useWorkspace();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const steps = info?.history.length ?? 0;

  const save = async () => {
    setBusy(true);
    try {
      const recipe = await api.recipe();
      const stem = recipe.source_file.replace(/\.[^.]+$/, "") || "data";
      const url = URL.createObjectURL(new Blob([JSON.stringify(recipe, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${stem}_recipe.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast({ tone: "success", title: "Recipe saved", description: `${pluralize(recipe.steps.length, "step")} saved. Apply it to the next file from the Overview page.` });
    } catch (err) {
      handleError(err, "Could not save the recipe");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BookOpen className="size-4 text-primary" aria-hidden="true" /> Cleaning recipe
        </CardTitle>
        <CardDescription>
          Save the {steps ? pluralize(steps, "step") : "steps"} you applied as a small .json file. Next time the same client sends a new file, open it and choose Apply recipe on the Overview page. The recipe contains only the steps, never your data.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button variant="secondary" onClick={save} loading={busy} disabled={!steps}>
          {!busy && <Download />} Save recipe (.json)
        </Button>
      </CardContent>
    </Card>
  );
}

/** Overview page: load a recipe, preview it on the current file and apply it. */
export function ApplyRecipeButton() {
  const { onSessionChanged, handleError } = useWorkspace();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [preview, setPreview] = useState<QuickCleanPreview | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [busy, setBusy] = useState<"preview" | "apply" | null>(null);

  const close = () => {
    setRecipe(null);
    setPreview(null);
    setError(null);
  };

  const fail = (err: unknown) => {
    const e = toApiError(err);
    if (SESSION_GONE.has(e.code)) {
      close();
      handleError(e);
    } else setError(e);
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setPreview(null);
    setError(null);
    try {
      setRecipe(parseRecipe(await file.text()));
    } catch (err) {
      setRecipe({ app: "CleanData Studio", kind: "cleaning-recipe", version: 1, name: file.name, source_file: "", created_at: "", steps: [] });
      setError(err instanceof Error ? err : new Error(String(err)));
    }
  };

  const runPreview = async () => {
    if (!recipe) return;
    setBusy("preview");
    setError(null);
    try {
      setPreview(await api.quickCleanPreview(recipe.steps));
    } catch (err) {
      fail(err);
    } finally {
      setBusy(null);
    }
  };

  const apply = async () => {
    if (!recipe || !preview) return;
    setBusy("apply");
    try {
      const res = await api.quickCleanApply(recipe.steps, preview.preview_token);
      onSessionChanged(res.session);
      toast({ tone: "success", title: "Recipe applied", description: `${pluralize(res.applied, "step")} applied. Each one can be undone.` });
      close();
    } catch (err) {
      setPreview(null);
      fail(err);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <input ref={input} type="file" accept=".json,application/json" className="hidden" onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = ""; }} />
      <Button variant="secondary" onClick={() => input.current?.click()}>
        <FileUp /> Apply recipe
      </Button>
      <Dialog
        open={!!recipe}
        onClose={close}
        className="max-h-[90vh] max-w-2xl overflow-y-auto"
        title={recipe?.name ?? "Recipe"}
        description={recipe?.source_file ? `Saved from ${recipe.source_file}. Preview it on this file, then apply.` : "Preview the recipe on this file, then apply."}
        footer={
          recipe && recipe.steps.length > 0 ? (
            <div className="flex w-full flex-wrap justify-end gap-2">
              <Button variant="secondary" onClick={runPreview} loading={busy === "preview"} disabled={busy !== null}>
                {busy !== "preview" && <Eye />} Preview
              </Button>
              <Button onClick={apply} loading={busy === "apply"} disabled={!preview || !!preview.blocked || busy !== null}>
                {busy !== "apply" && <Check />} Apply {pluralize(recipe.steps.length, "step")}
              </Button>
            </div>
          ) : undefined
        }
      >
        <div className="space-y-4">
          {recipe && recipe.steps.length > 0 && (
            <ol className="list-decimal space-y-1 rounded-md border border-border py-2.5 pr-3 pl-8 text-small">
              {recipe.steps.map((op, i) => (
                <li key={i}>
                  <span className="font-medium text-foreground">{stepLabel(op)}</span>
                  <span className="text-muted-foreground">{stepDetail(op)}</span>
                </li>
              ))}
            </ol>
          )}
          {error && (
            <Alert tone="danger" title={error.message}>
              {error instanceof ApiError && error.code === "unknown_columns"
                ? "This file does not have a column the recipe needs. Rename the column to match, or clean this file step by step."
                : error instanceof ApiError
                  ? error.hint
                  : "Choose a .json file saved with Save recipe on the Download page."}
            </Alert>
          )}
          {preview && (
            <Alert
              tone={preview.blocked ? "danger" : "success"}
              title={
                preview.blocked
                  ? "One step cannot be applied to this file"
                  : `If applied: rows ${formatNumber(preview.rows_before)} → ${formatNumber(preview.rows_after)}, ${formatNumber(preview.cells_changed)} cells changed`
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
