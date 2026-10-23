import { useEffect, useRef, useState, type DragEvent } from "react";
import { ChevronDown, FileSpreadsheet, FileUp, Lock, RotateCcw, Sparkles } from "lucide-react";
import { ApiError, uploadFile } from "@/api/client";
import type { ImportFormat } from "@/api/types";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ProgressBar, Spinner } from "@/components/ui/misc";
import { FieldHint, Input, Label, Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { keepText } from "@/lib/limits";
import { Link } from "@/lib/router";
import { SUPPORTED_EXTENSIONS, cn, formatBytes, formatDuration, formatFromName } from "@/lib/utils";
import { toApiError } from "./useAsync";
import { useWorkspace } from "./WorkspaceContext";

/** A small, deliberately messy dataset so new users can try every operation. */
export const SAMPLE_CSV = [
  "Customer ID,Full Name ,City,Signup Date,Monthly Spend,Plan",
  "1001,Ayesha Khan,Lahore,2024-01-15,4200,Basic",
  "1002,  Bilal Ahmed ,lahore,2024-02-03,,premium",
  "1003,Sara Malik,Karachi,2024-02-20,3900,Basic",
  "1003,Sara Malik,Karachi,2024-02-20,3900,Basic",
  "1004,Omar Farooq,ISLAMABAD,not available,5100,Premium",
  "1005,Zoya Hussain,Peshawar,2024-03-11,N/A,basic",
  "1006,Hamza Ali,Lahore,2024-03-18,4600,Basic",
  "1007,Fatima Noor,karachi,2024-04-02,98000,Premium",
  "1008,Usman Tariq,Multan,2024-04-09,3700,",
  "1009,Hina Shah,Islamabad,2024-04-21,4100,Basic",
  ",,,,,",
  "1010,Ali Raza,Quetta,2024-05-02,4450,premium",
].join("\n") + "\n";

export function UploadPanel() {
  const { onUploaded, config, notice } = useWorkspace();
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Real limits come from GET /api/config; the server re-checks every upload anyway.
  const maxMb = config?.max_upload_mb ?? 100;
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [processingSince, setProcessingSince] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<ApiError | null>(null);
  const [lastFile, setLastFile] = useState<File | null>(null);
  const [format, setFormat] = useState<ImportFormat | "auto">("auto");
  const [sheet, setSheet] = useState("");

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  // Large files can take a while to analyse after the upload finishes: show elapsed time.
  useEffect(() => {
    if (processingSince === null) return;
    const t = window.setInterval(() => setElapsed((Date.now() - processingSince) / 1000), 1000);
    return () => window.clearInterval(t);
  }, [processingSince]);

  const busy = progress !== null;

  const start = async (file: File, override: { format: ImportFormat | "auto"; sheet: string } = { format, sheet }) => {
    setError(null);
    setLastFile(file);
    const detected = formatFromName(file.name);
    if (!detected && override.format === "auto") {
      setError(
        new ApiError(
          `"${file.name}" is not a supported data file.`,
          "invalid_extension",
          0,
          "Supported formats: CSV, TSV, Excel (.xlsx, .xls) and JSON. PDFs, images and Word documents cannot be cleaned as tables.",
        ),
      );
      return;
    }
    if (file.size === 0) {
      setError(new ApiError("The file is empty.", "empty_file", 0, "Check that you exported the data correctly."));
      return;
    }
    if (file.size > maxMb * 1024 * 1024) {
      setError(
        new ApiError(
          `The file is ${formatBytes(file.size)}, above the ${maxMb} MB limit.`,
          "file_too_large",
          413,
          "Split the file into smaller parts or remove unneeded columns, then try again.",
        ),
      );
      return;
    }
    abortRef.current = new AbortController();
    setProgress(0);
    setProcessingSince(null);
    setElapsed(0);
    try {
      const res = await uploadFile(
        file,
        { format: override.format === "auto" ? null : override.format, sheet: override.sheet || null },
        (f) => {
          setProgress(f);
          if (f >= 1) setProcessingSince((p) => p ?? Date.now());
        },
        abortRef.current.signal,
      );
      toast({ tone: "success", title: "File imported", description: `${res.file.name} is ready to inspect.` });
      onUploaded(res);
    } catch (err) {
      const e = toApiError(err);
      if (e.code !== "aborted") setError(e);
    } finally {
      setProgress(null);
      setProcessingSince(null);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (busy) return;
    const file = e.dataTransfer.files?.[0];
    if (file) void start(file);
  };

  const useSample = () => void start(new File([SAMPLE_CSV], "sample_customers.csv", { type: "text/csv" }), { format: "auto", sheet: "" });

  return (
    <div className="mx-auto max-w-3xl py-6 sm:py-10">
      <div className="mb-6">
        <h1 className="text-h1 font-semibold tracking-tight">Upload a data file</h1>
        <p className="mt-1 text-body text-muted-foreground">No file uploaded yet. Start by uploading the dataset you want to inspect and clean.</p>
      </div>

      {notice && (
        <Alert tone="info" className="mb-4" title="Session ended">
          {notice}
        </Alert>
      )}

      <Card className="p-2">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            if (!busy) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            "flex flex-col items-center justify-center rounded-md border-2 border-dashed px-6 py-12 text-center transition-colors",
            dragging ? "border-primary bg-primary-soft" : "border-border-strong bg-canvas",
          )}
        >
          <span className="flex size-12 items-center justify-center rounded-lg bg-background text-primary shadow-card">
            <FileUp className="size-6" aria-hidden="true" />
          </span>
          {busy ? (
            <div className="mt-5 w-full max-w-xs">
              <p className="mb-3 truncate text-body font-medium">{lastFile?.name}</p>
              <ProgressBar value={progress ?? 0} label={processingSince ? "Uploaded" : `Uploading ${formatBytes(lastFile?.size ?? 0)}…`} />
              {processingSince ? (
                <div className="mt-3 space-y-1">
                  <Spinner label={`Reading and validating the file… ${formatDuration(elapsed)}`} />
                  <p className="text-caption text-muted-foreground">Large files (especially Excel) can take a minute. Keep this tab open.</p>
                </div>
              ) : (
                <Button variant="ghost" size="sm" className="mt-3" onClick={() => abortRef.current?.abort()}>
                  Cancel upload
                </Button>
              )}
            </div>
          ) : (
            <>
              <p className="mt-4 text-h3 font-medium">Drag and drop your data file here</p>
              <p className="mt-1 text-body text-muted-foreground">or choose a file from your computer</p>
              <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                <Button onClick={() => inputRef.current?.click()}>
                  <FileSpreadsheet /> Choose file
                </Button>
                <Button variant="secondary" onClick={useSample}>
                  <Sparkles /> Try sample data
                </Button>
              </div>
            </>
          )}
          <input
            ref={inputRef}
            type="file"
            accept={SUPPORTED_EXTENSIONS.join(",")}
            className="sr-only"
            aria-label="Choose data file"
            tabIndex={-1}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void start(file);
            }}
          />
        </div>
      </Card>

      <details className="group mt-3 rounded-md border border-border bg-background px-4 py-2.5 text-body">
        <summary className="flex cursor-pointer list-none items-center justify-between font-medium text-slate-700">
          Import options
          <ChevronDown className="size-4 text-slate-500 transition-transform group-open:rotate-180" aria-hidden="true" />
        </summary>
        <div className="mt-3 grid gap-4 pb-1 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="import-format">File format</Label>
            <Select id="import-format" value={format} disabled={busy} onChange={(e) => setFormat(e.target.value as ImportFormat | "auto")}>
              <option value="auto">Detect from file name (recommended)</option>
              <option value="csv">CSV (comma, semicolon or pipe separated)</option>
              <option value="tsv">TSV (tab separated)</option>
              <option value="xlsx">Excel workbook (.xlsx)</option>
              <option value="xls">Excel 97–2003 (.xls)</option>
              <option value="json">JSON / JSON Lines</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="import-sheet">Excel sheet name (optional)</Label>
            <Input id="import-sheet" value={sheet} disabled={busy} maxLength={255} onChange={(e) => setSheet(e.target.value)} placeholder="First sheet" />
            <FieldHint>Only used for Excel files. Leave empty to load the first sheet.</FieldHint>
          </div>
        </div>
      </details>

      {error && (
        <Alert
          tone="danger"
          className="mt-4"
          title={error.message}
          action={
            lastFile && !["invalid_extension", "file_too_large", "empty_file", "unsupported_content"].includes(error.code) ? (
              <Button variant="secondary" size="sm" onClick={() => void start(lastFile)}>
                <RotateCcw /> Try again
              </Button>
            ) : undefined
          }
        >
          {error.hint}
        </Alert>
      )}

      <dl className="mt-6 grid gap-3 text-body sm:grid-cols-3">
        {[
          { t: "Formats", d: "CSV, TSV, Excel (.xlsx, .xls) and JSON / JSON Lines." },
          { t: "Size limit", d: `Up to ${maxMb} MB per file (limit set by the server).` },
          { t: "Header row", d: "The first row (or JSON keys) should contain column names." },
        ].map((x) => (
          <div key={x.t} className="rounded-md border border-border bg-background px-4 py-3">
            <dt className="font-medium">{x.t}</dt>
            <dd className="mt-0.5 text-small text-muted-foreground">{x.d}</dd>
          </div>
        ))}
      </dl>

      <p className="mt-5 flex items-start gap-2 text-caption text-muted-foreground">
        <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        <span>
          Your file is processed on the CleanData Studio server: it is held in a temporary file only while it is imported,
          then {config?.save_sessions ? "saved on this computer" : "kept in memory"}. {keepText(config)} The full file is never sent to an AI.{" "}
          <Link href="/privacy" className="text-primary hover:underline">
            Privacy details
          </Link>
        </span>
      </p>
    </div>
  );
}
