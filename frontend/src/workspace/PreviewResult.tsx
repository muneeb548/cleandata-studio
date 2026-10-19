import { ArrowRight } from "lucide-react";
import type { OperationPreview } from "@/api/types";
import { Alert } from "@/components/ui/alert";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatNumber, pluralize } from "@/lib/utils";
import { RowsTable } from "./DataPanel";
import { Cell } from "./shared";

function Stat({ label, before, after }: { label: string; before: number; after: number }) {
  const changed = before !== after;
  return (
    <div className="rounded-md border border-border px-3 py-2">
      <p className="text-caption text-muted-foreground">{label}</p>
      <p className="tabular mt-0.5 flex items-center gap-1.5 text-body font-semibold">
        {formatNumber(before)}
        <ArrowRight className="size-3.5 text-slate-500" aria-label="becomes" />
        <span className={changed ? "text-primary" : undefined}>{formatNumber(after)}</span>
      </p>
    </div>
  );
}

/** Shows what an operation will change (preview) or did change (after apply). */
export function PreviewResult({ preview, mode }: { preview: OperationPreview; mode: "preview" | "applied" }) {
  const { changes, details } = preview;
  const invalid = details.invalid_samples ?? [];

  let tone: "danger" | "info" | "success" | "warning" = "success";
  let title = preview.summary;
  if (preview.blocked) {
    tone = "danger";
    title = "This operation cannot be applied as configured";
  } else if (!preview.changed) {
    tone = "info";
  } else if (mode === "preview") {
    tone = preview.destructive ? "warning" : "info";
    title = `If applied: ${preview.summary}`;
  }

  return (
    <div className="space-y-4">
      <Alert tone={tone} title={title}>
        {preview.blocked ? (
          <>
            {preview.blocked} <strong>Nothing was changed.</strong>
          </>
        ) : !preview.changed ? (
          "Nothing would change, so there is nothing to apply."
        ) : mode === "preview" ? (
          <>This is a preview — your data has not been modified yet.{preview.destructive && " Applying it will permanently remove data from the working dataset (you can still undo)."}</>
        ) : null}
      </Alert>

      {preview.warnings.length > 0 && (
        <Alert tone="warning" title="Please note">
          <ul className="list-disc space-y-0.5 pl-4">
            {preview.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Stat label="Rows" before={preview.rows_before} after={preview.rows_after} />
        <Stat label="Columns" before={preview.columns_before} after={preview.columns_after} />
        <div className="rounded-md border border-border px-3 py-2">
          <p className="text-caption text-muted-foreground">Cells changed</p>
          <p className="tabular mt-0.5 text-body font-semibold">{formatNumber(preview.cells_changed)}</p>
        </div>
      </div>

      {invalid.length > 0 && (
        <section aria-labelledby="invalid-title">
          <h3 id="invalid-title" className="mb-2 text-body font-semibold">
            {preview.operation.type === "standardize_phone"
              ? "Values that are not valid phone numbers"
              : preview.operation.type === "standardize_country"
                ? "Values that are not recognised countries"
                : preview.operation.type === "clean_email"
                  ? "Values that are not valid email addresses"
                  : preview.operation.type === "clean_numbers"
                    ? "Values that are not numbers"
                    : "Values that cannot be converted"}
            {details.invalid_counts && (
              <span className="ml-2 font-normal text-muted-foreground">
                ({Object.entries(details.invalid_counts).map(([c, n]) => `${c}: ${n}`).join(", ")})
              </span>
            )}
          </h3>
          <div className="scroll-thin max-h-64 overflow-auto rounded-md border border-border">
            <Table>
              <THead>
                <tr>
                  <TH scope="col">Row</TH>
                  <TH scope="col">Column</TH>
                  <TH scope="col">Value</TH>
                </tr>
              </THead>
              <tbody>
                {invalid.map((s, i) => (
                  <TR key={i}>
                    <TD className="tabular py-1.5 text-slate-500">{s.row}</TD>
                    <TD className="py-1.5">{s.column}</TD>
                    <TD className="max-w-64 py-1.5 text-danger">
                      <Cell value={s.value} />
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </div>
        </section>
      )}

      {changes.mapping && (
        <section aria-labelledby="mapping-title">
          <h3 id="mapping-title" className="mb-2 text-body font-semibold">Proposed column names</h3>
          <div className="scroll-thin max-h-72 overflow-auto rounded-md border border-border">
            <Table>
              <THead>
                <tr>
                  <TH scope="col">Current name</TH>
                  <TH scope="col" className="w-6 px-0" />
                  <TH scope="col">New name</TH>
                </tr>
              </THead>
              <tbody>
                {changes.mapping.map((m) => {
                  const same = m.before === m.after;
                  return (
                    <TR key={m.before}>
                      <TD className="py-1.5 font-mono text-caption whitespace-pre">“{m.before}”</TD>
                      <TD aria-hidden="true" className="w-6 px-0">
                        <ArrowRight className="size-3.5 text-slate-500" />
                      </TD>
                      <TD className="py-1.5 font-mono text-caption">
                        {same ? <span className="text-muted-foreground">unchanged</span> : <span className="font-semibold text-primary">{m.after}</span>}
                      </TD>
                    </TR>
                  );
                })}
              </tbody>
            </Table>
          </div>
        </section>
      )}

      {changes.removed_columns.length > 0 && (
        <section>
          <h3 className="mb-2 text-body font-semibold">Columns {mode === "preview" ? "to be removed" : "removed"}</h3>
          <div className="flex flex-wrap gap-1.5">
            {changes.removed_columns.map((c) => (
              <Badge key={c} tone="danger">
                {c}
              </Badge>
            ))}
          </div>
        </section>
      )}

      {changes.removed_rows && changes.removed_rows.rows.length > 0 && (
        <section>
          <h3 className="mb-2 text-body font-semibold">
            Rows {mode === "preview" ? "to be removed" : "removed"}
            {preview.rows_removed > changes.removed_rows.rows.length && (
              <span className="ml-2 font-normal text-muted-foreground">
                (first {changes.removed_rows.rows.length} of {pluralize(preview.rows_removed, "row")})
              </span>
            )}
          </h3>
          <div className="rounded-md border border-border">
            <RowsTable
              columns={changes.removed_rows.columns.map((name) => ({ name }))}
              rows={changes.removed_rows.rows}
              rowNumbers={changes.removed_rows.row_numbers}
              caption="Rows that will be removed"
              maxHeight="max-h-72"
            />
          </div>
        </section>
      )}

      {changes.cell_samples.length > 0 && (
        <section>
          <h3 className="mb-2 text-body font-semibold">
            Example cell changes
            {preview.cells_changed > changes.cell_samples.length && (
              <span className="ml-2 font-normal text-muted-foreground">
                (first {changes.cell_samples.length} of {formatNumber(preview.cells_changed)})
              </span>
            )}
          </h3>
          <div className="scroll-thin max-h-72 overflow-auto rounded-md border border-border">
            <Table className="w-full min-w-[480px]">
              <THead>
                <tr>
                  <TH scope="col">Row</TH>
                  <TH scope="col">Column</TH>
                  <TH scope="col">Before</TH>
                  <TH scope="col">After</TH>
                </tr>
              </THead>
              <tbody>
                {changes.cell_samples.map((c, i) => (
                  <TR key={i}>
                    <TD className="tabular py-1.5 text-slate-500">{c.row}</TD>
                    <TD className="max-w-40 truncate py-1.5" title={c.column}>
                      {c.column}
                    </TD>
                    <TD className="max-w-56 py-1.5 text-slate-500 line-through decoration-slate-300">
                      <Cell value={c.before} />
                    </TD>
                    <TD className="max-w-56 py-1.5 font-medium text-foreground">
                      <Cell value={c.after} />
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </div>
        </section>
      )}
    </div>
  );
}
