import { useEffect, useState } from "react";
import { Download, FileCheck } from "lucide-react";
import { ApiError, SESSION_GONE, api } from "@/api/client";
import { toApiError } from "./useAsync";
import type { ExportFormat } from "@/api/types";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page";
import { Checkbox, FieldHint, Input, Label, RadioCard } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { formatNumber, suggestedOutputName } from "@/lib/utils";
import { KeyValue } from "./shared";
import { AiSummaryCard } from "./Ai";
import { ChangeReportCard } from "./QuickClean";
import { RecipeCard } from "./Recipes";
import { DeleteDataButton } from "./DeleteDataButton";
import { useWorkspace } from "./WorkspaceContext";

export function ExportPanel() {
  const { info, config, handleError, setTab } = useWorkspace();
  const [downloaded, setDownloaded] = useState(false);
  const toast = useToast();
  const [name, setName] = useState("");
  const [bom, setBom] = useState(false);
  const [protectFormulas, setProtectFormulas] = useState(false);
  const [includeReport, setIncludeReport] = useState(true);
  const [highlight, setHighlight] = useState(false);
  const [format, setFormat] = useState<ExportFormat>("csv");
  const [busy, setBusy] = useState(false);
  const [downloadError, setDownloadError] = useState<ApiError | null>(null);

  useEffect(() => {
    if (info) setName(suggestedOutputName(info.file.name));
  }, [info?.file.name]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!info) return null;
  const { current_shape: cur, original_shape: orig, history } = info;
  const empty = cur.rows === 0 || cur.columns === 0;
  const EXCEL_MAX_ROWS = 1_048_575; // Excel's sheet limit, minus the header row
  const excelTooBig = cur.rows > EXCEL_MAX_ROWS;
  const slowExcel = format === "xlsx" && cur.rows * cur.columns > 2_000_000;

  const download = async () => {
    setBusy(true);
    setDownloadError(null);
    try {
      const saved = await api.exportFile(name, format, bom, protectFormulas, includeReport && history.length > 0, highlight);
      toast({ tone: "success", title: "Download ready", description: `${saved} was generated from the current working data.` });
      setDownloaded(true);
    } catch (err) {
      const e = toApiError(err);
      if (SESSION_GONE.has(e.code)) handleError(e);
      else setDownloadError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Download" description="The file is generated from the current working data, including every applied operation." />
      <div className="grid items-start gap-5 lg:grid-cols-2">

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileCheck className="size-4 text-primary" aria-hidden="true" /> Summary
          </CardTitle>
          <CardDescription>Check this before downloading.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4">
            <KeyValue label="Rows" value={`${formatNumber(cur.rows)} (was ${formatNumber(orig.rows)})`} />
            <KeyValue label="Columns" value={`${formatNumber(cur.columns)} (was ${formatNumber(orig.columns)})`} />
            <KeyValue label="Operations applied" value={formatNumber(history.length)} />
            <KeyValue label="Format" value={format === "csv" ? (bom ? "CSV, UTF-8 with BOM" : "CSV, UTF-8") : "Excel (.xlsx)"} />
          </dl>
          {history.length === 0 && (
            <Alert tone="info" className="mt-4" title="No cleaning operations applied" action={<Button size="sm" variant="secondary" onClick={() => setTab("clean")}>Go to cleaning</Button>}>
              The file will contain the same data as your upload.
            </Alert>
          )}
          {empty && (
            <Alert tone="warning" className="mt-4" title="The working dataset is empty">
              {cur.columns === 0 ? "All columns have been removed; the file will be empty." : "The file will contain only the header row."} Use Undo or Reset if this is not intended.
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Download className="size-4 text-primary" aria-hidden="true" /> File options
          </CardTitle>
          <CardDescription>Choose the format and name of the downloaded file.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <fieldset>
            <legend className="mb-2 text-small font-medium text-slate-700">File format</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <RadioCard name="export-format" value="csv" checked={format === "csv"} onChange={() => setFormat("csv")} label="CSV (.csv)" description="Universal, fastest, no size limit." />
              <RadioCard
                name="export-format"
                value="xlsx"
                checked={format === "xlsx"}
                onChange={() => setFormat("xlsx")}
                label="Excel (.xlsx)"
                description={excelTooBig ? "Too many rows for one Excel sheet." : "Keeps numbers and dates as Excel types."}
              />
            </div>
          </fieldset>
          {format === "xlsx" && excelTooBig && (
            <Alert tone="warning" title="Too many rows for Excel">
              Excel sheets hold at most {formatNumber(EXCEL_MAX_ROWS)} data rows; this dataset has {formatNumber(cur.rows)}. Download as CSV instead.
            </Alert>
          )}
          {slowExcel && !excelTooBig && (
            <Alert tone="info" title="Large Excel export">
              Writing {formatNumber(cur.rows * cur.columns)} cells to Excel can take a minute or more. CSV is much faster.
            </Alert>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="out-name">File name</Label>
            <div className="flex items-center gap-2">
              <Input id="out-name" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
              <span className="text-body text-muted-foreground">.{format}</span>
            </div>
            <FieldHint>Unsupported characters are replaced with underscores.</FieldHint>
          </div>
          {format === "xlsx" && history.length > 0 && (
            <Checkbox
              id="include-report"
              checked={includeReport}
              onChange={(e) => setIncludeReport(e.target.checked)}
              label="Add a “Cleaning report” sheet"
              description="A second sheet that lists every change and what is left for review, ready for your client."
            />
          )}
          {format === "xlsx" && (
            <Checkbox
              id="highlight"
              checked={highlight}
              onChange={(e) => setHighlight(e.target.checked)}
              label="Colour the cells that still need a look"
              description="Empty cells grey, “N/A”-style text, extra spaces and invalid emails yellow, duplicate rows orange, with a “Colour key” sheet. Like conditional formatting, but done for you."
            />
          )}
          {format === "csv" && (
            <Checkbox
              id="bom"
              checked={bom}
              onChange={(e) => setBom(e.target.checked)}
              label="Optimise for Microsoft Excel"
              description="Adds a UTF-8 byte order mark so Excel shows non-English characters (e.g. Urdu, Arabic, accents) correctly."
            />
          )}
          {format === "csv" && (
            <Checkbox
              id="protect-formulas"
              checked={protectFormulas}
              onChange={(e) => setProtectFormulas(e.target.checked)}
              label="Protect against spreadsheet formulas"
              description="Text starting with =, +, - or @ gets a leading apostrophe so spreadsheet apps don't run it as a formula. This changes those values, so leave it off if the file is for code or a database. Excel (.xlsx) exports are always stored as plain text."
            />
          )}
          {downloadError && (
            <Alert tone="danger" title="Download failed" action={<Button size="sm" variant="secondary" onClick={() => void download()}>Try again</Button>}>
              {downloadError.message} {downloadError.hint}
            </Alert>
          )}
          <Button size="lg" onClick={download} loading={busy} disabled={format === "xlsx" && excelTooBig} className="w-full sm:w-auto">
            <Download /> {busy ? "Preparing download…" : `Download ${format === "csv" ? "CSV" : "Excel"}`}
          </Button>
          {downloaded && (
            <Alert tone="success" title="Finished with this file?" action={<DeleteDataButton />}>
              {config && config.session_ttl_minutes > 0 && !config.save_sessions
                ? `Delete it from the server now instead of waiting ${config.session_ttl_minutes} minutes.`
                : "Delete it now if you no longer need it. It is kept until you do."}
            </Alert>
          )}
        </CardContent>
      </Card>
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-2">
        <ChangeReportCard />
        <RecipeCard />
        <AiSummaryCard />
      </div>
    </div>
  );
}
