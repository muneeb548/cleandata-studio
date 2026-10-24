import { useEffect, useRef, useState } from "react";
import { FilePlus, Plus, Trash2, X } from "lucide-react";
import { ApiError, addFile, api } from "@/api/client";
import type { AttachedFile, AttachedFilePreview, ColumnProfile } from "@/api/types";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox, FieldHint, Input, Label, RadioCard, Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { SUPPORTED_EXTENSIONS, cn, formatBytes, formatNumber, pluralize } from "@/lib/utils";
import { RowsTable } from "./DataPanel";
import { suggestJoinKey, type FormState } from "./operationForms";
import { ColumnPicker } from "./shared";
import { toApiError } from "./useAsync";
import { useWorkspace } from "./WorkspaceContext";

type Props = { form: FormState; set: (patch: Partial<FormState>) => void; cols: ColumnProfile[] };

/** Clean data → Combine files: add another file, then append its rows or join its columns. */
export function CombineFilesForm({ form, set, cols }: Props) {
  const { info, config, onSessionChanged, handleError } = useWorkspace();
  const toast = useToast();
  const files = info?.files ?? [];
  const selected = files.find((f) => f.id === form.cfFileId) ?? null;
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState<{ name: string; progress: number } | null>(null);
  const [uploadError, setUploadError] = useState<ApiError | null>(null);
  const [preview, setPreview] = useState<AttachedFilePreview | null>(null);

  // Forget a chosen file that is no longer on the server (removed, or a new session).
  useEffect(() => {
    if (form.cfFileId && !selected) set({ cfFileId: "", cfColumns: [], cfKeys: [{ left: "", right: "" }] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.cfFileId, selected]);

  // First rows of the chosen file, so the user can check it is the right one.
  useEffect(() => {
    setPreview(null);
    if (!selected) return;
    let live = true;
    api
      .filePreview(selected.id)
      .then((p) => live && setPreview(p))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [selected?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const choose = (file: AttachedFile) => {
    const patch: Partial<FormState> = { cfFileId: file.id, cfColumns: [] };
    const guess = suggestJoinKey(cols.map((c) => c.name), file.columns);
    patch.cfKeys = [guess ?? { left: "", right: "" }];
    set(patch);
  };

  const onPick = async (file: File | undefined) => {
    if (inputRef.current) inputRef.current.value = "";
    if (!file) return;
    setUploadError(null);
    const limit = config?.max_upload_mb;
    if (limit && file.size > limit * 1024 * 1024) {
      setUploadError(new ApiError(`The file is larger than the ${limit} MB limit.`, "file_too_large", 413, "Split the file into smaller parts."));
      return;
    }
    setUploading({ name: file.name, progress: 0 });
    try {
      const res = await addFile(file, {}, (progress) => setUploading({ name: file.name, progress }));
      onSessionChanged(res.session);
      choose(res.file);
      toast({ tone: "success", title: "File added", description: `${res.file.name}: ${pluralize(res.file.rows, "row")}, ${pluralize(res.file.columns.length, "column")}.` });
    } catch (err) {
      const e = toApiError(err);
      if (e.code === "session_expired" || e.code === "no_session") handleError(e);
      else setUploadError(e);
    } finally {
      setUploading(null);
    }
  };

  const remove = async (file: AttachedFile) => {
    try {
      const next = await api.removeFile(file.id);
      onSessionChanged(next);
      if (form.cfFileId === file.id) set({ cfFileId: "" });
    } catch (err) {
      handleError(err, "Could not remove the file");
    }
  };

  const otherCols = selected?.columns ?? [];
  const keys = form.cfKeys.length ? form.cfKeys : [{ left: "", right: "" }];
  const updateKey = (i: number, patch: Partial<(typeof keys)[number]>) => set({ cfKeys: keys.map((k, j) => (j === i ? { ...k, ...patch } : k)) });
  const bringable = otherCols.filter((c) => !keys.some((k) => k.right === c)).map((name) => ({ name, type: "text" as const }));

  return (
    <div className="space-y-5">
      <section className="space-y-2" aria-labelledby="cf-files">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="cf-files" className="text-small font-medium text-slate-700">
            File to combine with {info ? <span className="font-semibold">{info.file.name}</span> : "your data"}
          </h3>
          <Button variant="secondary" size="sm" onClick={() => inputRef.current?.click()} loading={!!uploading} disabled={!!uploading}>
            {!uploading && <FilePlus />} Add a file
          </Button>
          <input
            ref={inputRef}
            type="file"
            className="sr-only"
            accept={SUPPORTED_EXTENSIONS.join(",")}
            aria-label="Choose the file to combine"
            tabIndex={-1}
            onChange={(e) => void onPick(e.target.files?.[0])}
          />
        </div>
        {uploading && (
          <p className="text-caption text-muted-foreground" aria-live="polite">
            Uploading {uploading.name}… {Math.round(uploading.progress * 100)}%
          </p>
        )}
        {uploadError && (
          <Alert tone="danger" title={uploadError.message}>
            {uploadError.hint}
          </Alert>
        )}
        {files.length === 0 && !uploading ? (
          <p className="rounded-md border border-dashed border-border-strong px-4 py-5 text-center text-small text-muted-foreground">
            Add the other file (CSV, Excel or JSON), for example next month's orders or a list of emails with cities. It is kept in memory only, like your main file.
          </p>
        ) : (
          <ul className="space-y-2">
            {files.map((f) => (
              <li key={f.id} className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <RadioCard
                    name="cf-file"
                    value={f.id}
                    checked={form.cfFileId === f.id}
                    onChange={() => choose(f)}
                    label={<span className="break-all">{f.name}</span>}
                    description={`${pluralize(f.rows, "row")} · ${pluralize(f.columns.length, "column")} · ${formatBytes(f.size)}`}
                  />
                </div>
                <Button variant="ghost" size="icon" aria-label={`Remove ${f.name}`} onClick={() => void remove(f)}>
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}
        {selected && selected.warnings.length > 0 && (
          <Alert tone="warning" title="While reading this file">
            <ul className="list-disc pl-4">
              {selected.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </Alert>
        )}
        {preview && preview.id === selected?.id && preview.preview.rows.length > 0 && (
          <div className="rounded-md border border-border">
            <RowsTable
              columns={preview.preview.columns.map((name) => ({ name }))}
              rows={preview.preview.rows}
              rowNumbers={preview.preview.rows.map((_, i) => i + 1)}
              caption={`First rows of ${selected.name}`}
              maxHeight="max-h-56"
            />
          </div>
        )}
      </section>

      {selected && (
        <>
          <fieldset>
            <legend className="mb-2 text-small font-medium text-slate-700">How to combine</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <RadioCard
                name="cf-mode"
                value="append"
                checked={form.cfMode === "append"}
                onChange={() => set({ cfMode: "append" })}
                label="Add its rows below mine"
                description="Same kind of data, e.g. January + February orders. Columns are matched by name."
              />
              <RadioCard
                name="cf-mode"
                value="join"
                checked={form.cfMode === "join"}
                onChange={() => set({ cfMode: "join" })}
                label="Add its columns to matching rows"
                description="Like Excel VLOOKUP, e.g. bring each customer's city from another file by email."
              />
            </div>
          </fieldset>

          {form.cfMode === "append" ? (
            <div className="space-y-3">
              <Checkbox
                id="cf-source"
                checked={form.cfSourceOn}
                onChange={(e) => set({ cfSourceOn: e.target.checked })}
                label="Add a column that says which file each row came from"
              />
              {form.cfSourceOn && (
                <div className="max-w-xs space-y-1.5">
                  <Label htmlFor="cf-source-name">Column name</Label>
                  <Input id="cf-source-name" value={form.cfSourceName} maxLength={200} onChange={(e) => set({ cfSourceName: e.target.value })} />
                </div>
              )}
              <FieldHint>
                A column that exists in only one file is kept and left empty for the other file's rows. Rename columns first (Columns &amp; sorting → Organize) if the same information has different names.
              </FieldHint>
            </div>
          ) : (
            <div className="space-y-5">
              <fieldset className="space-y-2">
                <legend className="mb-1 text-small font-medium text-slate-700">Match rows where</legend>
                <ol className="space-y-2">
                  {keys.map((k, i) => (
                    <li key={i} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto] sm:items-center">
                      <Select aria-label={`Your column ${i + 1}`} value={k.left} onChange={(e) => updateKey(i, { left: e.target.value })}>
                        <option value="">Your column…</option>
                        {cols.map((c) => (
                          <option key={c.name} value={c.name} disabled={keys.some((o, j) => j !== i && o.left === c.name)}>
                            {c.name}
                          </option>
                        ))}
                      </Select>
                      <span className="text-center text-small text-muted-foreground">equals</span>
                      <Select aria-label={`Column in ${selected.name} ${i + 1}`} value={k.right} onChange={(e) => updateKey(i, { right: e.target.value })}>
                        <option value="">Column in {selected.name}…</option>
                        {otherCols.map((c) => (
                          <option key={c} value={c} disabled={keys.some((o, j) => j !== i && o.right === c)}>
                            {c}
                          </option>
                        ))}
                      </Select>
                      <Button variant="ghost" size="icon" aria-label={`Remove match ${i + 1}`} disabled={keys.length === 1} onClick={() => set({ cfKeys: keys.filter((_, j) => j !== i) })}>
                        <X />
                      </Button>
                    </li>
                  ))}
                </ol>
                {keys.length < 5 && (
                  <Button variant="link" size="sm" onClick={() => set({ cfKeys: [...keys, { left: "", right: "" }] })}>
                    <Plus /> Also match on another column
                  </Button>
                )}
                <Checkbox
                  id="cf-loose"
                  checked={form.cfLoose}
                  onChange={(e) => set({ cfLoose: e.target.checked })}
                  label="Ignore capitals and extra spaces"
                  description="“ALI@x.com ” matches “ali@x.com”. Empty values never match."
                />
              </fieldset>

              <ColumnPicker
                id="cf-cols"
                label={`Columns to bring from ${selected.name} (none selected = all)`}
                columns={bringable}
                selected={form.cfColumns.filter((c) => bringable.some((b) => b.name === c))}
                onChange={(cfColumns) => set({ cfColumns })}
              />

              <fieldset>
                <legend className="mb-2 text-small font-medium text-slate-700">Rows to keep</legend>
                <div className="grid gap-2 lg:grid-cols-3">
                  <RadioCard name="cf-how" value="left" checked={form.cfHow === "left"} onChange={() => set({ cfHow: "left" })} label="All my rows" description="Rows without a match get empty new columns." />
                  <RadioCard name="cf-how" value="inner" checked={form.cfHow === "inner"} onChange={() => set({ cfHow: "inner" })} label="Only rows that match" description="Removes my rows that have no match." />
                  <RadioCard name="cf-how" value="outer" checked={form.cfHow === "outer"} onChange={() => set({ cfHow: "outer" })} label="All rows from both files" description="Also adds rows of the other file that matched nothing." />
                </div>
              </fieldset>

              <fieldset>
                <legend className="mb-2 text-small font-medium text-slate-700">When a value appears more than once in {selected.name}</legend>
                <div className="grid gap-2 lg:grid-cols-3">
                  <RadioCard name="cf-dup" value="first" checked={form.cfDuplicates === "first"} onChange={() => set({ cfDuplicates: "first" })} label="Use the first match" description="Like VLOOKUP: the number of rows stays the same." />
                  <RadioCard name="cf-dup" value="all" checked={form.cfDuplicates === "all"} onChange={() => set({ cfDuplicates: "all" })} label="Use every match" description="My row is repeated once per match, e.g. one row per order." />
                  <RadioCard name="cf-dup" value="stop" checked={form.cfDuplicates === "stop"} onChange={() => set({ cfDuplicates: "stop" })} label="Stop and show me the values" description="For a lookup list where each value must appear once, e.g. one tier per customer." />
                </div>
              </fieldset>

              <div className="space-y-3">
                <Checkbox
                  id="cf-match"
                  checked={form.cfMatchOn}
                  onChange={(e) => set({ cfMatchOn: e.target.checked })}
                  label="Add a column that shows whether each row matched"
                  description="Each row gets “matched”, “no match” or “empty key”, so you can filter or flag the rows without a match."
                />
                {form.cfMatchOn && (
                  <div className="max-w-xs space-y-1.5">
                    <Label htmlFor="cf-match-name">Column name</Label>
                    <Input id="cf-match-name" value={form.cfMatchName} maxLength={200} onChange={(e) => set({ cfMatchName: e.target.value })} />
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
      {selected && (
        <p className={cn("text-caption text-muted-foreground")}>
          {selected.name} has {formatNumber(selected.rows)} rows. It is never changed itself; only your working data is.
        </p>
      )}
    </div>
  );
}
