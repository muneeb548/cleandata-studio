import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowDownUp,
  ArrowUp,
  CaseSensitive,
  Check,
  CheckCircle2,
  Copy,
  Eye,
  FileSpreadsheet,
  Flag,
  History,
  Info,
  Phone,
  Plus,
  Replace,
  Split,
  SquareDashed,
  TableProperties,
  Trash2,
  Type,
  Undo2,
  X,
  type LucideIcon,
} from "lucide-react";
import { ApiError, SESSION_GONE, api } from "@/api/client";
import { AiSuggestMappings } from "./Ai";
import { CombineFilesForm } from "./CombineFiles";
import { CurrencyConvert } from "./CurrencyConvert";
import type { ColumnProfile, ColumnValues, FlagRule, Operation, OperationPreview, OutlierReport, Profile } from "@/api/types";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Checkbox, FieldHint, Input, Label, RadioCard, Select } from "@/components/ui/form";
import { EmptyState, LoadingBlock } from "@/components/ui/misc";
import { PageHeader } from "@/components/ui/page";
import { Segmented } from "@/components/ui/segmented";
import { useToast } from "@/components/ui/toast";
import { cn, formatNumber, pluralize } from "@/lib/utils";
import {
  CATEGORIES,
  CHOICES,
  DEFAULT_FORM,
  FLAG_CHECKS,
  PHONE_REGIONS,
  buildOperation,
  categoryOf,
  mappingRows,
  columnRestriction,
  formForIssue,
  isNumeric,
  missingWords,
  type CategoryId,
  type CleanChoice,
  type FormState,
} from "./operationForms";
import { PreviewResult } from "./PreviewResult";
import { Cell, ColumnPicker } from "./shared";
import { toApiError, useAsync } from "./useAsync";
import { useWorkspace } from "./WorkspaceContext";

const CATEGORY_ICONS: Record<CategoryId, LucideIcon> = {
  duplicates: Copy,
  missing: SquareDashed,
  text: CaseSensitive,
  columns: TableProperties,
  types: Type,
  outliers: ArrowDownUp,
  empty: Trash2,
  replace: Replace,
  split: Split,
  phone: Phone,
  flags: Flag,
  combine: FileSpreadsheet,
};

const EXPLANATIONS: Record<CleanChoice, string> = {
  remove_duplicates: "Deletes rows that are exact copies of another row. You choose which copy to keep.",
  missing_values: "Fills empty cells with a value you choose, or removes rows or columns that contain them.",
  trim_whitespace: "Removes spaces before and after text, so “ Lahore ” and “Lahore” become the same value.",
  standardize_text: "Makes capitalisation consistent, so “lahore”, “LAHORE” and “Lahore” are treated alike.",
  clean_column_names: "Removes stray spaces from headers and makes every column name unique and code-friendly.",
  convert_type: "Turns text columns into numbers, dates or text. Values that cannot be converted are listed first.",
  outliers: "Flags numbers far outside the typical range (IQR method). Review only — your data is never changed here.",
  remove_empty: "Removes rows and columns in which every cell is empty.",
  find_replace: "Replaces a specific value or piece of text in the columns you choose.",
  split_column: "Splits one column into several new columns, for example a full name into first and last name.",
  merge_columns: "Joins several columns into one new column, for example first and last name into a full name.",
  standardize_phone: "Writes phone numbers from any country in one format and lists the ones that are not real numbers.",
  standardize_country: "Writes every country the same way, so “USA”, “U.S.A.” and “america” all become “United States”.",
  clean_email: "Tidies email addresses and lists the ones that cannot be real, so they can be fixed or flagged.",
  clean_numbers: "Turns amounts written as text, in any currency or number style, into real numbers.",
  map_values: "Shows every different value in a column so you can rename many of them at once.",
  near_duplicates: "Finds rows that are the same record written slightly differently, and marks or removes them.",
  flag_rows: "Marks rows that need a human decision in a new column, without changing or removing any data.",
  organize_columns: "Renames, removes and reorders columns, for example to match the columns a CRM or another system expects.",
  sort_rows: "Sorts the rows by one or more columns. Numbers sort as numbers, dates as dates, and the download keeps this order.",
  mark_missing: "Turns words that mean “no value” (Unknown, TBD, ---) into real empty cells, so they count as missing and can be filled.",
  combine_files: "Adds another file to your data: its rows below yours, or its columns next to matching rows (like VLOOKUP). The other file is never changed.",
};

const SHORT_LABELS: Partial<Record<CleanChoice, string>> = {
  trim_whitespace: "Trim spaces",
  standardize_text: "Change case",
  split_column: "Split",
  merge_columns: "Merge",
  standardize_phone: "Phone numbers",
  clean_email: "Emails",
  standardize_country: "Country names",
  convert_type: "Convert type",
  clean_numbers: "Amounts & currencies",
  find_replace: "Find & replace",
  map_values: "Map many values",
  remove_duplicates: "Exact copies",
  near_duplicates: "Near-duplicates",
  organize_columns: "Organize",
  sort_rows: "Sort rows",
  clean_column_names: "Tidy names",
  missing_values: "Fill or remove",
  mark_missing: "Mark as missing",
};

function StepIndicator({ step }: { step: 1 | 2 | 3 }) {
  const steps = ["Configure", "Preview", "Apply"];
  return (
    <ol className="flex items-center gap-1.5 text-caption" aria-label="Progress">
      {steps.map((label, i) => {
        const n = i + 1;
        const done = n < step || (n === 3 && step === 3);
        const current = n === step && !done;
        return (
          <li key={label} className="flex items-center gap-1.5">
            {i > 0 && <span className="h-px w-3 bg-border-strong" aria-hidden="true" />}
            <span
              className={cn(
                "flex items-center gap-1 rounded-full px-2 py-0.5 font-medium",
                done && "bg-success-soft text-green-800",
                current && "bg-primary-soft text-blue-800",
                !done && !current && "text-slate-500",
              )}
              aria-current={current ? "step" : undefined}
            >
              {done ? <Check className="size-3" aria-hidden="true" /> : <span className="tabular">{n}</span>}
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function OperationForm({ choice, form, set, profile }: { choice: CleanChoice; form: FormState; set: (patch: Partial<FormState>) => void; profile: Profile }) {
  const cols = profile.columns;
  const restrict = (c: ColumnProfile) => columnRestriction(choice, form, c);

  switch (choice) {
    case "remove_duplicates":
      return (
        <div className="space-y-4">
          <p className="text-body text-muted-foreground">
            Rows are duplicates when every value matches an earlier row exactly. The working data currently has{" "}
            <strong className="text-foreground">{formatNumber(profile.stats.duplicate_rows)}</strong> duplicate {profile.stats.duplicate_rows === 1 ? "row" : "rows"}.
          </p>
          <fieldset className="space-y-2">
            <legend className="mb-2 text-small font-medium text-slate-700">Which copy should be kept?</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <RadioCard name="keep" value="first" checked={form.keep === "first"} onChange={() => set({ keep: "first" })} label="Keep first occurrence" description="Later copies are removed." />
              <RadioCard name="keep" value="last" checked={form.keep === "last"} onChange={() => set({ keep: "last" })} label="Keep last occurrence" description="Earlier copies are removed." />
            </div>
          </fieldset>
        </div>
      );

    case "missing_values":
      return (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="mv-strategy">Action</Label>
            <Select id="mv-strategy" value={form.mvStrategy} onChange={(e) => set({ mvStrategy: e.target.value as FormState["mvStrategy"] })}>
              <option value="fill_constant">Fill with a value</option>
              <option value="fill_mean">Fill numeric columns with the mean</option>
              <option value="fill_median">Fill numeric columns with the median</option>
              <option value="drop_rows">Remove rows that have missing values</option>
              <option value="drop_columns">Remove columns that have missing values</option>
            </Select>
            <FieldHint>
              {form.mvStrategy === "drop_rows" && "A row is removed if any selected column is empty in that row."}
              {form.mvStrategy === "drop_columns" && "Only selected columns that actually contain missing values are removed."}
              {(form.mvStrategy === "fill_mean" || form.mvStrategy === "fill_median") && "Only numeric columns can be selected. The value is calculated from the non-missing values."}
              {form.mvStrategy === "fill_constant" && "Only empty cells in the selected columns are filled. Other values are not touched."}
            </FieldHint>
          </div>
          {form.mvStrategy === "fill_constant" && (
            <div className="space-y-1.5">
              <Label htmlFor="mv-value">Fill value</Label>
              <Input id="mv-value" value={form.mvValue} maxLength={500} onChange={(e) => set({ mvValue: e.target.value })} placeholder="e.g. 0 or Unknown" />
            </div>
          )}
          <ColumnPicker
            id="mv-cols"
            columns={cols}
            selected={form.mvColumns}
            onChange={(mvColumns) => set({ mvColumns })}
            disabledReason={restrict}
            showMissing
          />
        </div>
      );

    case "trim_whitespace":
      return (
        <div className="space-y-4">
          <p className="text-body text-muted-foreground">Removes spaces at the start and end of text values. Spaces inside values are kept. Cells containing only spaces become missing.</p>
          <Checkbox id="trim-all" checked={form.trimAll} onChange={(e) => set({ trimAll: e.target.checked })} label="Apply to all text columns" />
          {!form.trimAll && <ColumnPicker id="trim-cols" columns={cols} selected={form.trimColumns} onChange={(trimColumns) => set({ trimColumns })} disabledReason={restrict} />}
        </div>
      );

    case "standardize_text":
      return (
        <div className="space-y-4">
          <fieldset>
            <legend className="mb-2 text-small font-medium text-slate-700">Convert to</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              <RadioCard name="case" value="lower" checked={form.caseMode === "lower"} onChange={() => set({ caseMode: "lower" })} label="lowercase" />
              <RadioCard name="case" value="upper" checked={form.caseMode === "upper"} onChange={() => set({ caseMode: "upper" })} label="UPPERCASE" />
              <RadioCard name="case" value="title" checked={form.caseMode === "title"} onChange={() => set({ caseMode: "title" })} label="Title Case" />
            </div>
          </fieldset>
          <ColumnPicker id="case-cols" columns={cols} selected={form.caseColumns} onChange={(caseColumns) => set({ caseColumns })} disabledReason={restrict} />
          <FieldHint>Missing values stay missing.</FieldHint>
        </div>
      );

    case "organize_columns":
      return <OrganizeColumnsForm form={form} set={set} cols={cols} />;

    case "sort_rows":
      return <SortRowsForm form={form} set={set} cols={cols} />;

    case "mark_missing": {
      const words = missingWords(form.mmWords);
      return (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="mm-words">Words that mean “no value”</Label>
            <Input id="mm-words" value={form.mmWords} maxLength={2000} onChange={(e) => set({ mmWords: e.target.value })} />
            <FieldHint>
              Separate them with commas. Capitals and outer spaces are ignored.{" "}
              {words.length > 0 && `${pluralize(words.length, "word")}: ${words.slice(0, 8).map((w) => `“${w}”`).join(", ")}${words.length > 8 ? " …" : ""}`}
            </FieldHint>
          </div>
          <ColumnPicker id="mm-cols" columns={cols} selected={form.mmColumns} onChange={(mmColumns) => set({ mmColumns })} disabledReason={restrict} />
          <FieldHint>Only whole cells are matched: “Unknown” becomes empty, “Unknown street” stays as it is. “N/A”, “null” and similar are already counted as missing.</FieldHint>
        </div>
      );
    }

    case "clean_column_names":
      return (
        <div className="space-y-3">
          <p className="text-body text-muted-foreground">Leading and trailing spaces are always removed. If two names would become identical, a number is added so every name stays unique. Preview to see the proposed names.</p>
          <Checkbox id="cn-spaces" checked={form.replaceSpaces} onChange={(e) => set({ replaceSpaces: e.target.checked })} label="Replace spaces with underscores" description="“First Name” becomes “First_Name”." />
          <Checkbox id="cn-lower" checked={form.lowercase} onChange={(e) => set({ lowercase: e.target.checked })} label="Convert names to lowercase" description="“First_Name” becomes “first_name”." />
        </div>
      );

    case "convert_type":
      return (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="conv-target">Convert to</Label>
              <Select id="conv-target" value={form.convTarget} onChange={(e) => set({ convTarget: e.target.value as FormState["convTarget"] })}>
                <option value="integer">Integer (whole numbers)</option>
                <option value="float">Decimal number</option>
                <option value="string">Text</option>
                <option value="datetime">Date / time</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="conv-error">If a value cannot be converted</Label>
              <Select id="conv-error" value={form.convOnError} onChange={(e) => set({ convOnError: e.target.value as FormState["convOnError"] })}>
                <option value="abort">Stop and show me the values</option>
                <option value="set_missing">Set it to missing (reported)</option>
              </Select>
            </div>
          </div>
          {form.convTarget === "datetime" && (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="conv-format">Date format (optional)</Label>
                <Input id="conv-format" value={form.convFormat} onChange={(e) => set({ convFormat: e.target.value })} placeholder="e.g. %d/%m/%Y" maxLength={50} />
                <FieldHint>Leave empty to detect automatically. Uses Python strftime codes.</FieldHint>
              </div>
              <Checkbox id="conv-dayfirst" className="sm:mt-7" checked={form.convDayfirst} disabled={!!form.convFormat.trim()} onChange={(e) => set({ convDayfirst: e.target.checked })} label="Day comes first" description="Read 05/01/2024 as 5 January." />
            </div>
          )}
          <ColumnPicker id="conv-cols" columns={cols} selected={form.convColumns} onChange={(convColumns) => set({ convColumns })} />
        </div>
      );

    case "remove_empty":
      return (
        <div className="space-y-4">
          <p className="text-body text-muted-foreground">
            Currently <strong className="text-foreground">{formatNumber(profile.stats.empty_rows)}</strong> completely empty {profile.stats.empty_rows === 1 ? "row" : "rows"} and{" "}
            <strong className="text-foreground">{formatNumber(profile.stats.empty_columns)}</strong> completely empty {profile.stats.empty_columns === 1 ? "column" : "columns"}.
          </p>
          <fieldset>
            <legend className="mb-2 text-small font-medium text-slate-700">Remove</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              <RadioCard name="empty" value="both" checked={form.emptyTarget === "both"} onChange={() => set({ emptyTarget: "both" })} label="Rows and columns" />
              <RadioCard name="empty" value="rows" checked={form.emptyTarget === "rows"} onChange={() => set({ emptyTarget: "rows" })} label="Empty rows only" />
              <RadioCard name="empty" value="columns" checked={form.emptyTarget === "columns"} onChange={() => set({ emptyTarget: "columns" })} label="Empty columns only" />
            </div>
          </fieldset>
        </div>
      );

    case "find_replace":
      return (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="fr-find">Find</Label>
              <Input id="fr-find" value={form.frFind} maxLength={1000} onChange={(e) => set({ frFind: e.target.value })} placeholder="e.g. N/A" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="fr-replace">Replace with</Label>
              <Input id="fr-replace" value={form.frReplace} maxLength={1000} onChange={(e) => set({ frReplace: e.target.value })} placeholder="Leave empty to mark as missing" />
            </div>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <RadioCard name="match" value="exact" checked={form.frMatch === "exact"} onChange={() => set({ frMatch: "exact" })} label="Whole cell matches" description="Replace cells equal to the text." />
            <RadioCard name="match" value="contains" checked={form.frMatch === "contains"} onChange={() => set({ frMatch: "contains" })} label="Cell contains text" description="Replace the text inside cells." />
          </div>
          <Checkbox id="fr-case" checked={form.frCaseSensitive} onChange={(e) => set({ frCaseSensitive: e.target.checked })} label="Match case" />
          <ColumnPicker id="fr-cols" columns={cols} selected={form.frColumns} onChange={(frColumns) => set({ frColumns })} disabledReason={restrict} />
        </div>
      );

    case "split_column": {
      const textCols = cols.filter((c) => c.is_text);
      const setName = (i: number, v: string) => set({ splitNames: form.splitNames.map((n, j) => (j === i ? v : n)) });
      return (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="split-col">Column to split</Label>
              <Select id="split-col" value={form.splitColumn} onChange={(e) => set({ splitColumn: e.target.value })}>
                <option value="">Choose a text column…</option>
                {textCols.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="split-sep">Split on</Label>
              <Select
                id="split-sep"
                value={[" ", ",", "-", "/", "|", ";"].includes(form.splitSeparator) ? form.splitSeparator : "custom"}
                onChange={(e) => set({ splitSeparator: e.target.value === "custom" ? "" : e.target.value })}
              >
                <option value=" ">Spaces</option>
                <option value=",">Comma ( , )</option>
                <option value="-">Dash ( - )</option>
                <option value="/">Slash ( / )</option>
                <option value="|">Pipe ( | )</option>
                <option value=";">Semicolon ( ; )</option>
                <option value="custom">Other text…</option>
              </Select>
              {![" ", ",", "-", "/", "|", ";"].includes(form.splitSeparator) && (
                <Input aria-label="Custom separator" value={form.splitSeparator} maxLength={20} onChange={(e) => set({ splitSeparator: e.target.value })} placeholder="e.g. ' - '" />
              )}
            </div>
          </div>
          <fieldset className="space-y-2">
            <legend className="mb-2 text-small font-medium text-slate-700">New column names</legend>
            {form.splitNames.map((n, i) => (
              <div key={i} className="flex gap-2">
                <Input aria-label={`New column ${i + 1}`} value={n} maxLength={200} onChange={(e) => setName(i, e.target.value)} />
                {form.splitNames.length > 2 && (
                  <Button variant="ghost" size="icon" aria-label={`Remove column ${i + 1}`} onClick={() => set({ splitNames: form.splitNames.filter((_, j) => j !== i) })}>
                    <X />
                  </Button>
                )}
              </div>
            ))}
            {form.splitNames.length < 10 && (
              <Button variant="link" size="sm" onClick={() => set({ splitNames: [...form.splitNames, `part_${form.splitNames.length + 1}`] })}>
                <Plus /> Add another column
              </Button>
            )}
          </fieldset>
          <fieldset>
            <legend className="mb-2 text-small font-medium text-slate-700">When there are more parts than columns</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <RadioCard name="split-from" value="start" checked={form.splitFrom === "start"} onChange={() => set({ splitFrom: "start" })} label="Extra text goes to the last column" description="“Ali Raza Khan” → “Ali” + “Raza Khan”" />
              <RadioCard name="split-from" value="end" checked={form.splitFrom === "end"} onChange={() => set({ splitFrom: "end" })} label="Extra text goes to the first column" description="“Ali Raza Khan” → “Ali Raza” + “Khan”" />
            </div>
          </fieldset>
          <Checkbox id="split-keep" checked={form.splitKeep} onChange={(e) => set({ splitKeep: e.target.checked })} label="Keep the original column" description="Untick to remove it after splitting." />
        </div>
      );
    }

    case "merge_columns":
      return (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="merge-name">New column name</Label>
              <Input id="merge-name" value={form.mergeName} maxLength={200} onChange={(e) => set({ mergeName: e.target.value })} placeholder="e.g. full_name" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="merge-sep">Put between the values</Label>
              <Input id="merge-sep" value={form.mergeSeparator} maxLength={20} onChange={(e) => set({ mergeSeparator: e.target.value })} placeholder="a space" />
              <FieldHint>Empty values are skipped, so no double spaces appear.</FieldHint>
            </div>
          </div>
          <ColumnPicker id="merge-cols" label="Columns, in the order they are joined" columns={cols} selected={form.mergeColumns} onChange={(mergeColumns) => set({ mergeColumns })} />
          <Checkbox id="merge-keep" checked={form.mergeKeep} onChange={(e) => set({ mergeKeep: e.target.checked })} label="Keep the original columns" description="Untick to remove them after merging." />
        </div>
      );

    case "standardize_phone":
      return (
        <div className="space-y-4">
          <fieldset>
            <legend className="mb-2 text-small font-medium text-slate-700">Which country is each number from?</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <RadioCard name="phone-source" value="fixed" checked={form.phoneRegionSource === "fixed"} onChange={() => set({ phoneRegionSource: "fixed" })} label="The same country for every row" description="Best when all customers are from one country." />
              <RadioCard
                name="phone-source"
                value="column"
                checked={form.phoneRegionSource === "column"}
                onChange={() => set({ phoneRegionSource: "column", phoneRegionColumn: form.phoneRegionColumn || (cols.find((c) => /countr/i.test(c.name))?.name ?? "") })}
                label="Read it from a column"
                description="Best for mixed countries, e.g. a “country” column."
              />
            </div>
          </fieldset>
          {form.phoneRegionSource === "column" && (
            <div className="space-y-1.5">
              <Label htmlFor="phone-region-col">Country column</Label>
              <Select id="phone-region-col" value={form.phoneRegionColumn} onChange={(e) => set({ phoneRegionColumn: e.target.value })}>
                <option value="">Choose a column…</option>
                {cols.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </Select>
              <FieldHint>Understands names and codes such as USA, U.K., Deutschland, PK or Pakistan.</FieldHint>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="phone-region">{form.phoneRegionSource === "column" ? "If a row's country is empty or unknown, use" : "Country of numbers without a + code"}</Label>
              <Select id="phone-region" value={form.phoneRegion} onChange={(e) => set({ phoneRegion: e.target.value })}>
                {PHONE_REGIONS.map((code) => (
                  <option key={code} value={code}>
                    {regionName(code)} ({code})
                  </option>
                ))}
              </Select>
              <FieldHint>Numbers that already start with + or 00 are read correctly for every country.</FieldHint>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="phone-format">Write numbers as</Label>
              <Select id="phone-format" value={form.phoneFormat} onChange={(e) => set({ phoneFormat: e.target.value as FormState["phoneFormat"] })}>
                <option value="international">International: +1 650-253-0000</option>
                <option value="national">National: (650) 253-0000</option>
                <option value="e164">E.164 (for CRMs and SMS tools): +16502530000</option>
              </Select>
            </div>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <RadioCard name="phone-invalid" value="keep" checked={form.phoneOnInvalid === "keep"} onChange={() => set({ phoneOnInvalid: "keep" })} label="Leave invalid numbers as they are" description="They are listed so you can review or flag them." />
            <RadioCard name="phone-invalid" value="set_missing" checked={form.phoneOnInvalid === "set_missing"} onChange={() => set({ phoneOnInvalid: "set_missing" })} label="Make invalid numbers empty" description="Use only when the client asked for it." />
          </div>
          <ColumnPicker id="phone-cols" columns={cols} selected={form.phoneColumns} onChange={(phoneColumns) => set({ phoneColumns })} />
        </div>
      );

    case "standardize_country":
      return (
        <div className="space-y-4">
          <fieldset>
            <legend className="mb-2 text-small font-medium text-slate-700">Write countries as</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <RadioCard name="country-output" value="name" checked={form.countryOutput === "name"} onChange={() => set({ countryOutput: "name" })} label="Full names" description="USA, U.S.A., america → United States" />
              <RadioCard name="country-output" value="code" checked={form.countryOutput === "code"} onChange={() => set({ countryOutput: "code" })} label="Two-letter codes" description="United States → US, Germany → DE (ISO)" />
            </div>
          </fieldset>
          <p className="text-caption text-muted-foreground">Knows every country, plus common spellings, local names and three-letter codes. Values it does not recognise are left as they are and listed.</p>
          <ColumnPicker id="country-cols" columns={cols} selected={form.countryColumns} onChange={(countryColumns) => set({ countryColumns })} disabledReason={restrict} />
        </div>
      );

    case "clean_email":
      return (
        <div className="space-y-4">
          <p className="text-body text-muted-foreground">Removes spaces and “mailto:”, and lists addresses that cannot be real (for example “ali@gmail” or “ali@@gmail.com”).</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Checkbox id="email-lower" checked={form.emailLowercase} onChange={(e) => set({ emailLowercase: e.target.checked })} label="Use lowercase" description="ALI@Gmail.com → ali@gmail.com" />
            <Checkbox id="email-fix" checked={form.emailFixDomains} onChange={(e) => set({ emailFixDomains: e.target.checked })} label="Fix common provider typos" description="gmial.com → gmail.com, hotmail.con → hotmail.com" />
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <RadioCard name="email-invalid" value="keep" checked={form.emailOnInvalid === "keep"} onChange={() => set({ emailOnInvalid: "keep" })} label="Keep invalid addresses" description="They are listed so you can review or flag them." />
            <RadioCard name="email-invalid" value="set_missing" checked={form.emailOnInvalid === "set_missing"} onChange={() => set({ emailOnInvalid: "set_missing" })} label="Make invalid addresses empty" description="Use only when the client asked for it." />
          </div>
          <ColumnPicker id="email-cols" columns={cols} selected={form.emailColumns} onChange={(emailColumns) => set({ emailColumns })} disabledReason={restrict} />
        </div>
      );

    case "clean_numbers":
      return (
        <div className="space-y-4">
          <p className="text-body text-muted-foreground">Removes currency signs and codes ($, €, £, Rs, PKR, USD…), spaces and thousands separators, and reads (500) as −500. The result is a real number column you can sum and sort.</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="num-decimal">Decimal mark</Label>
              <Select id="num-decimal" value={form.numDecimal} onChange={(e) => set({ numDecimal: e.target.value as FormState["numDecimal"] })}>
                <option value="auto">Detect for each value</option>
                <option value=".">Dot: 1,234.56 (US, UK, Pakistan, India)</option>
                <option value=",">Comma: 1.234,56 (most of Europe)</option>
              </Select>
            </div>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <RadioCard name="num-error" value="abort" checked={form.numOnError === "abort"} onChange={() => set({ numOnError: "abort" })} label="Stop and show me the values" description="Nothing changes if any value is not a number." />
            <RadioCard name="num-error" value="set_missing" checked={form.numOnError === "set_missing"} onChange={() => set({ numOnError: "set_missing" })} label="Set them to missing (reported)" description="Converts everything else." />
          </div>
          <ColumnPicker id="num-cols" columns={cols} selected={form.numColumns} onChange={(numColumns) => set({ numColumns })} />
          <CurrencyConvert form={form} set={set} cols={cols} />
        </div>
      );

    case "map_values":
      return <MapValuesForm form={form} set={set} cols={cols} />;

    case "near_duplicates":
      return (
        <div className="space-y-4">
          <p className="text-body text-muted-foreground">
            Finds rows that describe the same person or thing even when they are written differently, for example “Ali Khan, ali@gmail.com” and “ali  khan., ALI@gmail.com ”.
          </p>
          <ColumnPicker id="nd-cols" label="Columns that identify a record" columns={cols} selected={form.ndColumns} onChange={(ndColumns) => set({ ndColumns })} />
          <fieldset>
            <legend className="mb-2 text-small font-medium text-slate-700">How close must they be?</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <RadioCard name="nd-match" value="normalized" checked={form.ndMatch === "normalized"} onChange={() => set({ ndMatch: "normalized" })} label="Same after cleanup" description="Ignores capitals, accents, spaces and punctuation. Very safe." />
              <RadioCard name="nd-match" value="similar" checked={form.ndMatch === "similar"} onChange={() => set({ ndMatch: "similar" })} label="Also small spelling differences" description="“Jon Smith” and “John Smith”. Always review the groups." />
            </div>
          </fieldset>
          <fieldset>
            <legend className="mb-2 text-small font-medium text-slate-700">What should happen?</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <RadioCard name="nd-action" value="flag" checked={form.ndAction === "flag"} onChange={() => set({ ndAction: "flag" })} label="Mark them with a group number" description="Adds a column; nothing is removed. Recommended." />
              <RadioCard name="nd-action" value="remove" checked={form.ndAction === "remove"} onChange={() => set({ ndAction: "remove" })} label="Keep only the first row of each group" description="Removes the other rows. Preview carefully." />
            </div>
          </fieldset>
          {form.ndAction === "flag" && (
            <div className="space-y-1.5 sm:max-w-xs">
              <Label htmlFor="nd-name">Group column name</Label>
              <Input id="nd-name" value={form.ndColumnName} maxLength={200} onChange={(e) => set({ ndColumnName: e.target.value })} />
            </div>
          )}
        </div>
      );

    case "combine_files":
      return <CombineFilesForm form={form} set={set} cols={cols} />;
    case "flag_rows":
      return <FlagRulesForm form={form} set={set} cols={cols} />;

    case "outliers":
      return null;
  }
}

const regionNames = (() => {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" });
  } catch {
    return null;
  }
})();
function regionName(code: string): string {
  try {
    return regionNames?.of(code) ?? code;
  } catch {
    return code;
  }
}

function MapValuesForm({ form, set, cols }: { form: FormState; set: (patch: Partial<FormState>) => void; cols: ColumnProfile[] }) {
  const { handleError } = useWorkspace();
  const [values, setValues] = useState<ColumnValues | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const textCols = cols.filter((c) => c.is_text);

  useEffect(() => {
    if (!form.mapColumn) {
      setValues(null);
      return;
    }
    let active = true;
    setLoading(true);
    api
      .values(form.mapColumn)
      .then((v) => active && setValues(v))
      .catch((err) => active && handleError(err, "Could not load the values"))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.mapColumn]);

  const shown = (values?.values ?? []).filter((v) => v.value.toLowerCase().includes(filter.toLowerCase()));
  const changes = mappingRows(form.mapEdits).length;
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="map-col">Column</Label>
          <Select id="map-col" value={form.mapColumn} onChange={(e) => set({ mapColumn: e.target.value, mapEdits: {} })}>
            <option value="">Choose a text column…</option>
            {textCols.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </Select>
        </div>
        <Checkbox id="map-case" className="sm:mt-7" checked={form.mapIgnoreCase} onChange={(e) => set({ mapIgnoreCase: e.target.checked })} label="Ignore capitals and outer spaces" description="“ISB”, “isb ” and “Isb” follow the same row." />
      </div>
      {values && !loading && values.distinct > 1 && (
        <AiSuggestMappings column={form.mapColumn} edits={form.mapEdits} onEdits={(mapEdits) => set({ mapEdits })} />
      )}
      {loading && <LoadingBlock />}
      {values && !loading && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-small text-muted-foreground">
              {formatNumber(values.distinct)} different values{values.truncated ? `; showing the ${formatNumber(values.values.length)} most common` : ""}. Type the new value next to the ones to change{changes ? ` (${changes} so far)` : ""}.
            </p>
            {values.values.length > 8 && (
              <Input className="max-w-56" aria-label="Filter values" placeholder="Filter values" value={filter} onChange={(e) => setFilter(e.target.value)} />
            )}
          </div>
          <div className="scroll-thin max-h-80 overflow-auto rounded-md border border-border">
            <Table>
              <THead>
                <tr>
                  <TH scope="col" className="pl-3">Current value</TH>
                  <TH scope="col" className="text-right">Rows</TH>
                  <TH scope="col" className="pr-3">Change to</TH>
                </tr>
              </THead>
              <tbody>
                {shown.map((v) => (
                  <TR key={v.value}>
                    <TD className="pl-3 font-medium text-foreground">{v.value}</TD>
                    <TD className="tabular text-right text-slate-500">{formatNumber(v.count)}</TD>
                    <TD className="pr-3">
                      <Input
                        aria-label={`New value for ${v.value}`}
                        value={form.mapEdits[v.value] ?? ""}
                        maxLength={1000}
                        placeholder="keep as is"
                        onChange={(e) => set({ mapEdits: { ...form.mapEdits, [v.value]: e.target.value } })}
                      />
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </div>
        </div>
      )}
    </div>
  );
}

function OrganizeColumnsForm({ form, set, cols }: { form: FormState; set: (patch: Partial<FormState>) => void; cols: ColumnProfile[] }) {
  const names = cols.map((c) => c.name);
  const signature = names.join("\u0000");
  useEffect(() => {
    const valid = form.orgOrder.length === names.length && form.orgOrder.every((n) => names.includes(n));
    if (!valid) set({ orgOrder: names, orgRenames: {}, orgDrop: [] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);
  const order = form.orgOrder.length === names.length ? form.orgOrder : names;
  const move = (i: number, step: -1 | 1) => {
    const j = i + step;
    if (j < 0 || j >= order.length) return;
    const next = [...order];
    [next[i], next[j]] = [next[j], next[i]];
    set({ orgOrder: next });
  };
  const toggleDrop = (name: string, on: boolean) => set({ orgDrop: on ? [...form.orgDrop, name] : form.orgDrop.filter((d) => d !== name) });
  const changes = order.filter((c) => (form.orgRenames[c] ?? "").trim() && form.orgRenames[c].trim() !== c).length + form.orgDrop.length;
  return (
    <div className="space-y-3">
      <p className="text-body text-muted-foreground">
        Type a new name, tick <em>Remove</em>, or use the arrows to change the order. Useful when a CRM or another system expects exact column names.
        {changes > 0 && ` ${pluralize(changes, "change")} so far.`}
      </p>
      <div className="scroll-thin max-h-96 overflow-auto rounded-md border border-border">
        <Table>
          <THead>
            <tr>
              <TH scope="col" className="w-10 pl-3">#</TH>
              <TH scope="col">Column</TH>
              <TH scope="col">New name</TH>
              <TH scope="col" className="text-center">Move</TH>
              <TH scope="col" className="pr-3">Remove</TH>
            </tr>
          </THead>
          <tbody>
            {order.map((name, i) => {
              const dropped = form.orgDrop.includes(name);
              return (
                <TR key={name} className={dropped ? "bg-danger-soft/40" : undefined}>
                  <TD className="tabular pl-3 text-slate-500">{i + 1}</TD>
                  <TD className={cn("max-w-48 truncate font-medium", dropped ? "text-slate-400 line-through" : "text-foreground")} title={name}>
                    {name}
                  </TD>
                  <TD>
                    <Input
                      aria-label={`New name for ${name}`}
                      value={form.orgRenames[name] ?? ""}
                      maxLength={200}
                      placeholder="keep name"
                      disabled={dropped}
                      onChange={(e) => set({ orgRenames: { ...form.orgRenames, [name]: e.target.value } })}
                    />
                  </TD>
                  <TD className="whitespace-nowrap text-center">
                    <Button variant="ghost" size="icon" aria-label={`Move ${name} up`} disabled={i === 0} onClick={() => move(i, -1)}>
                      <ArrowUp />
                    </Button>
                    <Button variant="ghost" size="icon" aria-label={`Move ${name} down`} disabled={i === order.length - 1} onClick={() => move(i, 1)}>
                      <ArrowDown />
                    </Button>
                  </TD>
                  <TD className="pr-3">
                    <Checkbox id={`org-drop-${i}`} checked={dropped} onChange={(e) => toggleDrop(name, e.target.checked)} label={<span className="sr-only">Remove {name}</span>} />
                  </TD>
                </TR>
              );
            })}
          </tbody>
        </Table>
      </div>
      {(form.orgDrop.length > 0 || changes > 0) && (
        <Button variant="link" size="sm" onClick={() => set({ orgOrder: names, orgRenames: {}, orgDrop: [] })}>
          Start over
        </Button>
      )}
    </div>
  );
}

function SortRowsForm({ form, set, cols }: { form: FormState; set: (patch: Partial<FormState>) => void; cols: ColumnProfile[] }) {
  const keys = form.sortKeys.length ? form.sortKeys : [{ column: "", direction: "asc" as const }];
  const update = (i: number, patch: Partial<(typeof keys)[number]>) => set({ sortKeys: keys.map((k, j) => (j === i ? { ...k, ...patch } : k)) });
  const typeOf = (name: string) => cols.find((c) => c.name === name)?.type;
  const words = (name: string, dir: "asc" | "desc") => {
    const t = typeOf(name);
    if (t === "integer" || t === "decimal") return dir === "asc" ? "Smallest first" : "Largest first";
    if (t === "datetime") return dir === "asc" ? "Oldest first" : "Newest first";
    return dir === "asc" ? "A to Z" : "Z to A";
  };
  return (
    <div className="space-y-4">
      <ol className="space-y-2">
        {keys.map((k, i) => (
          <li key={i} className="grid gap-2 sm:grid-cols-[auto_minmax(0,1fr)_minmax(0,12rem)_auto] sm:items-end">
            <span className="text-small text-muted-foreground sm:pb-2">{i === 0 ? "Sort by" : "then by"}</span>
            <Select aria-label={`Sort column ${i + 1}`} value={k.column} onChange={(e) => update(i, { column: e.target.value })}>
              <option value="">Choose a column…</option>
              {cols.map((c) => (
                <option key={c.name} value={c.name} disabled={keys.some((o, j) => j !== i && o.column === c.name)}>
                  {c.name}
                </option>
              ))}
            </Select>
            <Select aria-label={`Sort direction ${i + 1}`} value={k.direction} onChange={(e) => update(i, { direction: e.target.value as "asc" | "desc" })}>
              <option value="asc">{words(k.column, "asc")}</option>
              <option value="desc">{words(k.column, "desc")}</option>
            </Select>
            <Button variant="ghost" size="icon" aria-label={`Remove sort column ${i + 1}`} disabled={keys.length === 1} onClick={() => set({ sortKeys: keys.filter((_, j) => j !== i) })}>
              <X />
            </Button>
          </li>
        ))}
      </ol>
      {keys.length < 5 && (
        <Button variant="secondary" size="sm" onClick={() => set({ sortKeys: [...keys, { column: "", direction: "asc" }] })}>
          <Plus /> Add a tie-breaker column
        </Button>
      )}
      <fieldset>
        <legend className="mb-2 text-small font-medium text-slate-700">Rows with an empty value</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          <RadioCard name="sort-missing" value="last" checked={form.sortMissing === "last"} onChange={() => set({ sortMissing: "last" })} label="At the end" />
          <RadioCard name="sort-missing" value="first" checked={form.sortMissing === "first"} onChange={() => set({ sortMissing: "first" })} label="At the top" />
        </div>
      </fieldset>
      <FieldHint>Text is sorted ignoring capitals. Row numbers in the preview still refer to the uploaded file.</FieldHint>
    </div>
  );
}

function FlagRulesForm({ form, set, cols }: { form: FormState; set: (patch: Partial<FormState>) => void; cols: ColumnProfile[] }) {
  const [column, setColumn] = useState("");
  const [check, setCheck] = useState<FlagRule["check"]>("missing");
  const [min, setMin] = useState("");
  const [max, setMax] = useState("");
  const isRange = check === "out_of_range";
  const exists = form.flagRules.some((r) => r.column === column && r.check === check);
  const rangeMissing = isRange && !min.trim() && !max.trim();
  const add = () => {
    if (!column || exists || rangeMissing) return;
    set({ flagRules: [...form.flagRules, isRange ? { column, check, min: min.trim() || null, max: max.trim() || null } : { column, check }] });
  };
  const describe = (r: FlagRule) => {
    const base = FLAG_CHECKS.find((c) => c.value === r.check)!.label;
    if (r.check !== "out_of_range") return base;
    if (r.min && r.max) return `Outside ${r.min} to ${r.max}`;
    return r.min ? `Below ${r.min}` : `Above ${r.max}`;
  };
  const usesPhone = form.flagRules.some((r) => r.check === "invalid_phone");
  return (
    <div className="space-y-4">
      <p className="text-body text-muted-foreground">
        Adds one column that explains why each row needs attention, for example “Missing phone; Invalid email in email”. Your data is not changed and nothing is removed.
      </p>
      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
        <div className="space-y-1.5">
          <Label htmlFor="flag-col">Column</Label>
          <Select id="flag-col" value={column} onChange={(e) => setColumn(e.target.value)}>
            <option value="">Choose a column…</option>
            {cols.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="flag-check">Flag rows where</Label>
          <Select id="flag-check" value={check} onChange={(e) => setCheck(e.target.value as FlagRule["check"])}>
            {FLAG_CHECKS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </Select>
        </div>
        <Button variant="secondary" onClick={add} disabled={!column || exists || rangeMissing}>
          <Plus /> Add check
        </Button>
      </div>
      {isRange && (
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="flag-min">Smallest allowed value</Label>
            <Input id="flag-min" value={min} maxLength={50} placeholder="e.g. 0 or 2024-01-01" onChange={(e) => setMin(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="flag-max">Largest allowed value</Label>
            <Input id="flag-max" value={max} maxLength={50} placeholder="e.g. 100 or 2024-12-31" onChange={(e) => setMax(e.target.value)} />
          </div>
          <FieldHint className="sm:col-span-2">Fill one or both. Use numbers (age 0 to 100) or dates (orders in 2024). Values that are not numbers or dates are checked by “Not a number” / “Not a date”.</FieldHint>
        </div>
      )}
      {form.flagRules.length > 0 ? (
        <ul className="divide-y divide-border rounded-md border border-border">
          {form.flagRules.map((r, i) => (
            <li key={`${r.column}-${r.check}`} className="flex items-center justify-between gap-2 px-3 py-2 text-small">
              <span>
                <strong className="font-medium">{r.column}</strong>: {describe(r)}
              </span>
              <Button variant="ghost" size="icon" aria-label={`Remove check ${r.column} ${r.check}`} onClick={() => set({ flagRules: form.flagRules.filter((_, j) => j !== i) })}>
                <X />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-caption text-muted-foreground">No checks yet. Add one or more above.</p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="flag-name">Review column name</Label>
          <Input id="flag-name" value={form.flagColumnName} maxLength={200} onChange={(e) => set({ flagColumnName: e.target.value })} />
        </div>
        {usesPhone && (
          <div className="space-y-1.5">
            <Label htmlFor="flag-region-col">Country column for phone checks (optional)</Label>
            <Select id="flag-region-col" value={form.flagRegionColumn} onChange={(e) => set({ flagRegionColumn: e.target.value })}>
              <option value="">None</option>
              {cols.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </Select>
          </div>
        )}
        {usesPhone && (
          <div className="space-y-1.5">
            <Label htmlFor="flag-region">{form.flagRegionColumn ? "If a row's country is empty or unknown, use" : "Country of phone numbers without a + code"}</Label>
            <Select id="flag-region" value={form.flagRegion} onChange={(e) => set({ flagRegion: e.target.value })}>
              <option value="">None: only accept numbers with a + country code</option>
              {PHONE_REGIONS.map((code) => (
                <option key={code} value={code}>
                  {regionName(code)} ({code})
                </option>
              ))}
            </Select>
          </div>
        )}
      </div>
    </div>
  );
}

function OutlierReview({ profile, form, set }: { profile: Profile; form: FormState; set: (p: Partial<FormState>) => void }) {
  const numeric = profile.columns.filter(isNumeric);
  const [report, setReport] = useState<OutlierReport | null>(null);
  const [loading, setLoading] = useState(false);
  const { handleError } = useWorkspace();
  const column = numeric.some((c) => c.name === form.outlierColumn) ? form.outlierColumn : (numeric[0]?.name ?? "");

  const run = async () => {
    setLoading(true);
    try {
      setReport(await api.outliers(column));
    } catch (err) {
      setReport(null);
      handleError(err, "Could not check outliers");
    } finally {
      setLoading(false);
    }
  };

  if (!numeric.length) {
    return <EmptyState title="No numeric columns" className="py-8">Outlier detection needs at least one numeric column. Convert a column to a number first.</EmptyState>;
  }
  return (
    <div className="space-y-4">
      <Alert tone="info" title="Review only">
        Values below Q1 − 1.5×IQR or above Q3 + 1.5×IQR are flagged. An outlier is not necessarily an error — it may be a real, important value. This check never changes your data.
      </Alert>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1 space-y-1.5">
          <Label htmlFor="out-col">Numeric column</Label>
          <Select id="out-col" value={column} onChange={(e) => { set({ outlierColumn: e.target.value }); setReport(null); }}>
            {numeric.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </Select>
        </div>
        <Button onClick={run} loading={loading}>
          <Eye /> Detect outliers
        </Button>
      </div>
      {report && (
        <div className="space-y-3">
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              ["Values checked", formatNumber(report.checked)],
              ["Outliers", formatNumber(report.count)],
              ["Lower bound", Number(report.lower_bound.toPrecision(8)).toString()],
              ["Upper bound", Number(report.upper_bound.toPrecision(8)).toString()],
            ].map(([k, v]) => (
              <div key={k} className="rounded-md border border-border px-3 py-2">
                <dt className="text-caption text-muted-foreground">{k}</dt>
                <dd className="tabular text-body font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
          {report.count === 0 ? (
            <Alert tone="success" title="No outliers found in this column" />
          ) : (
            <div className="scroll-thin max-h-72 overflow-auto rounded-md border border-border">
              <Table>
                <THead>
                  <tr>
                    <TH scope="col">Row</TH>
                    <TH scope="col">Value</TH>
                    <TH scope="col">Position</TH>
                  </tr>
                </THead>
                <tbody>
                  {report.outliers.map((o) => (
                    <TR key={o.row}>
                      <TD className="tabular py-1.5 text-slate-500">{o.row}</TD>
                      <TD className="tabular py-1.5 font-medium">
                        <Cell value={o.value} />
                      </TD>
                      <TD className="py-1.5 text-muted-foreground">{o.position === "above" ? "Above upper bound" : "Below lower bound"}</TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
          {report.count > report.outliers.length && <FieldHint>Showing the {report.outliers.length} most extreme values.</FieldHint>}
        </div>
      )}
    </div>
  );
}

function CleaningHistory() {
  const { info, undo, setTab, pending } = useWorkspace();
  const [showLog, setShowLog] = useState(false);
  const history = info?.history ?? [];
  const log = info?.log ?? [];
  const reverted = log.filter((e) => e.event !== "applied").length;
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <History className="size-4 text-slate-500" aria-hidden="true" /> Cleaning history
        </CardTitle>
        <Button variant="ghost" size="sm" disabled={!info?.can_undo || pending !== null} loading={pending === "undo"} onClick={() => void undo()} aria-label="Undo the last step in the history">
          {pending !== "undo" && <Undo2 />} Undo
        </Button>
      </CardHeader>
      {history.length === 0 ? (
        <p className="px-5 py-4 text-small text-muted-foreground">No operations applied. The working data matches the original upload.</p>
      ) : (
        <ol className="scroll-thin max-h-80 divide-y divide-border overflow-y-auto">
          {history.map((h, i) => (
            <li key={h.id} className="px-5 py-2.5">
              <p className="flex items-center gap-2 text-small font-medium">
                <CheckCircle2 className="size-3.5 shrink-0 text-success" aria-hidden="true" />
                <span className="tabular text-muted-foreground">{i + 1}.</span> {h.label}
              </p>
              <p className="mt-0.5 pl-5.5 text-caption text-muted-foreground">{h.summary}</p>
              {!h.undoable && i < history.length - 1 && (
                <p className="mt-0.5 pl-5.5 text-micro text-slate-500">Removed from memory — can no longer be undone (Reset still works).</p>
              )}
            </li>
          ))}
        </ol>
      )}
      {log.length > 0 && (
        <div className="border-t border-border px-5 py-2.5">
          <button type="button" className="text-caption font-medium text-primary hover:underline" aria-expanded={showLog} onClick={() => setShowLog((v) => !v)}>
            {showLog ? "Hide activity log" : `Show activity log (${pluralize(log.length, "event")}${reverted ? `, ${reverted} undone/reset` : ""})`}
          </button>
          {showLog && (
            <ol className="mt-2 space-y-1.5">
              {log.map((e, i) => (
                <li key={i} className="flex items-start gap-2 text-caption">
                  <Badge tone={e.event === "applied" ? "success" : e.event === "undone" ? "warning" : "neutral"} className="mt-px shrink-0 capitalize">
                    {e.event}
                  </Badge>
                  <span className="text-slate-600">
                    {e.label ?? "Reset to original"}
                    <span className="block text-micro text-slate-500">{new Date(e.at * 1000).toLocaleTimeString()}</span>
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
      {history.length > 0 && (
        <div className="border-t border-border px-5 py-2.5">
          <Button variant="link" size="sm" onClick={() => setTab("compare")}>
            Compare with original
          </Button>
        </div>
      )}
    </Card>
  );
}

export function CleanPanel() {
  const { version, request, onSessionChanged, handleError, pending } = useWorkspace();
  const toast = useToast();
  const { data: profile, error, reload } = useAsync(() => api.profile("current", true), [version], version);
  const [choice, setChoice] = useState<CleanChoice>("remove_duplicates");
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [preview, setPreview] = useState<{ op: Operation; result: OperationPreview } | null>(null);
  // The result card belongs to the dataset version it produced; undo/reset make it stale.
  const [applied, setApplied] = useState<{ result: OperationPreview; version: number } | null>(null);
  const lastApplied = applied && applied.version === version ? applied.result : null;
  const setLastApplied = (result: OperationPreview | null, forVersion = version) =>
    setApplied(result ? { result, version: forVersion } : null);
  const [busy, setBusy] = useState<"preview" | "apply" | null>(null);
  // Failure of the last preview/apply, shown inside the operation card (not just as a toast).
  const [opError, setOpError] = useState<{ stage: "preview" | "apply"; error: ApiError } | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const built = useMemo(() => buildOperation(choice, form), [choice, form]);
  // A preview is only valid for the exact options it was made with.
  const previewIsCurrent = !!preview && !!built.operation && JSON.stringify(preview.op) === JSON.stringify(built.operation);

  // Prefill from a "Fix" button in the overview, once per click. The profile reloads after
  // every apply/undo; without this check the old request ran again and jumped back to it.
  const handledRequest = useRef<number | null>(null);
  useEffect(() => {
    if (!request || !profile || handledRequest.current === request.nonce) return;
    handledRequest.current = request.nonce;
    setChoice(request.type);
    // Flag checks collect: each "Flag" click from the Overview adds its check to the ones already chosen.
    setForm((f) => formForIssue(request.type, request.column, request.issueId, profile.columns, { ...DEFAULT_FORM, outlierColumn: f.outlierColumn, flagRules: request.type === "flag_rows" ? f.flagRules : DEFAULT_FORM.flagRules }, request.example));
    setPreview(null);
    setLastApplied(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.nonce, !!profile]);

  // Any change to the working data (apply, undo, reset) makes an open preview stale.
  useEffect(() => {
    setPreview(null);
    setOpError(null);
  }, [version]);

  // Drop selections for columns that no longer exist (e.g. after renaming).
  useEffect(() => {
    if (!profile) return;
    const names = new Set(profile.columns.map((c) => c.name));
    const keep = (arr: string[]) => arr.filter((n) => names.has(n));
    setForm((f) => ({
      ...f,
      mvColumns: keep(f.mvColumns),
      trimColumns: keep(f.trimColumns),
      caseColumns: keep(f.caseColumns),
      convColumns: keep(f.convColumns),
      frColumns: keep(f.frColumns),
      mergeColumns: keep(f.mergeColumns),
      phoneColumns: keep(f.phoneColumns),
      countryColumns: keep(f.countryColumns),
      emailColumns: keep(f.emailColumns),
      numColumns: keep(f.numColumns),
      numCountryColumn: names.has(f.numCountryColumn) ? f.numCountryColumn : "",
      mapColumn: names.has(f.mapColumn) ? f.mapColumn : "",
      ndColumns: keep(f.ndColumns),
      phoneRegionColumn: names.has(f.phoneRegionColumn) ? f.phoneRegionColumn : "",
      flagRegionColumn: names.has(f.flagRegionColumn) ? f.flagRegionColumn : "",
      splitColumn: names.has(f.splitColumn) ? f.splitColumn : "",
      flagRules: f.flagRules.filter((r) => names.has(r.column)),
    }));
  }, [profile]);

  const set = (patch: Partial<FormState>) => {
    setForm((f) => ({ ...f, ...patch }));
    setLastApplied(null);
    setOpError(null);
  };

  const fail = (stage: "preview" | "apply", err: unknown) => {
    const e = toApiError(err);
    if (SESSION_GONE.has(e.code)) {
      handleError(e); // returns the user to the upload screen
      return;
    }
    setOpError({ stage, error: e });
    if (e.code === "preview_outdated" || e.code === "preview_required") setPreview(null);
    if (e.code === "unknown_columns") reload(); // the column list may be stale
  };

  const select = (c: CleanChoice) => {
    setChoice(c);
    setPreview(null);
    setLastApplied(null);
    setOpError(null);
  };

  // Remember the last operation used inside each category (e.g. Trim vs Change case).
  const [lastInCategory, setLastInCategory] = useState<Partial<Record<CategoryId, CleanChoice>>>({});
  useEffect(() => setLastInCategory((m) => ({ ...m, [categoryOf(choice)]: choice })), [choice]);
  const selectCategory = (id: CategoryId) => {
    const cat = CATEGORIES.find((c) => c.id === id)!;
    select(lastInCategory[id] ?? cat.choices[0]);
  };

  const runPreview = async () => {
    if (!built.operation) return;
    setBusy("preview");
    setOpError(null);
    try {
      const result = await api.preview(built.operation);
      setPreview({ op: built.operation, result });
      setLastApplied(null);
    } catch (err) {
      fail("preview", err);
    } finally {
      setBusy(null);
    }
  };

  const apply = async () => {
    if (!preview) return;
    setConfirmOpen(false);
    setBusy("apply");
    setOpError(null);
    try {
      const res = await api.apply(preview.op, preview.result.preview_token);
      if (res.applied) {
        setLastApplied(res, version + 1);
        onSessionChanged(res.session);
        toast({ tone: "success", title: "Operation applied", description: res.summary });
      } else {
        toast({ tone: "info", title: "Nothing changed", description: res.summary });
      }
      setPreview(null);
    } catch (err) {
      fail("apply", err);
    } finally {
      setBusy(null);
    }
  };

  if (!profile) {
    return (
      <div className="space-y-6">
        <PageHeader title="Clean data" />
        {error ? (
          <Alert tone="danger" title={error.message} action={<Button size="sm" variant="secondary" onClick={reload}>Retry</Button>}>
            {error.hint}
          </Alert>
        ) : (
          <LoadingBlock />
        )}
      </div>
    );
  }

  const active = CHOICES.find((c) => c.id === choice)!;
  const category = CATEGORIES.find((c) => c.id === categoryOf(choice))!;
  const ActiveIcon = CATEGORY_ICONS[category.id];
  const canApply = previewIsCurrent && preview!.result.changed && !preview!.result.blocked;
  const step = lastApplied ? 3 : previewIsCurrent ? 2 : 1;
  const status = built.error
    ? { tone: "warning" as const, text: built.error }
    : !previewIsCurrent
      ? { tone: "neutral" as const, text: "Preview the changes before applying." }
      : preview!.result.blocked
        ? { tone: "danger" as const, text: "This configuration cannot be applied. See the details below." }
        : !preview!.result.changed
          ? { tone: "neutral" as const, text: "Nothing would change, so there is nothing to apply." }
          : { tone: "success" as const, text: "Preview ready. Review the changes, then apply." };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Clean data"
        description="Choose an operation, preview exactly what will change, then apply it. Every step can be undone."
      />

      <div className="grid gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <div className="space-y-5">
          {/* Phones and tablets: compact select */}
          <div className="space-y-1.5 lg:hidden">
            <Label htmlFor="op-select">Operation</Label>
            <Select id="op-select" value={category.id} onChange={(e) => selectCategory(e.target.value as CategoryId)}>
              {CATEGORIES.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </Select>
          </div>
          {/* Desktop: category list */}
          <Card className="hidden overflow-hidden lg:block">
            <p className="eyebrow border-b border-border px-4 py-2.5">Operations</p>
            <nav aria-label="Cleaning operations">
              <ul className="p-1.5">
                {CATEGORIES.map((c) => {
                  const Icon = CATEGORY_ICONS[c.id];
                  const selected = c.id === category.id;
                  return (
                    <li key={c.id}>
                      <button
                        type="button"
                        onClick={() => selectCategory(c.id)}
                        aria-current={selected ? "true" : undefined}
                        className={cn(
                          "flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left transition-colors",
                          selected ? "bg-primary-soft" : "hover:bg-muted",
                        )}
                      >
                        <Icon className={cn("size-4 shrink-0", selected ? "text-primary" : "text-slate-500")} aria-hidden="true" />
                        <span className="min-w-0">
                          <span className={cn("block text-small font-medium", selected ? "text-blue-900" : "text-foreground")}>{c.label}</span>
                          <span className="block truncate text-caption text-muted-foreground">{c.description}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </nav>
          </Card>
          <div className="hidden lg:block">
            <CleaningHistory />
          </div>
        </div>

        <div className="min-w-0 space-y-5">
          <Card>
            <CardHeader className="gap-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary">
                    <ActiveIcon className="size-[18px]" aria-hidden="true" />
                  </span>
                  <div>
                    <CardTitle>{category.choices.length > 1 ? category.label : active.label}</CardTitle>
                    <CardDescription>{EXPLANATIONS[choice]}</CardDescription>
                  </div>
                </div>
                {choice !== "outliers" && <StepIndicator step={step} />}
              </div>
              {category.choices.length > 1 && (
                <Segmented
                  label={`${category.label} operation`}
                  value={choice}
                  onChange={(c) => select(c)}
                  options={category.choices.map((c) => ({ value: c, label: SHORT_LABELS[c] ?? CHOICES.find((x) => x.id === c)!.label }))}
                  className="self-start"
                />
              )}
            </CardHeader>
            {choice === "outliers" ? (
              <CardContent>
                <OutlierReview profile={profile} form={form} set={set} />
              </CardContent>
            ) : (
              <>
                <CardContent>
                  <OperationForm choice={choice} form={form} set={set} profile={profile} />
                </CardContent>
                <div className="flex flex-col gap-3 border-t border-border bg-canvas px-5 py-3 sm:flex-row sm:items-center">
                  <p
                    className={cn(
                      "flex flex-1 items-center gap-1.5 text-small",
                      status.tone === "warning" && "text-amber-800",
                      status.tone === "danger" && "text-red-700",
                      status.tone === "success" && "text-green-800",
                      status.tone === "neutral" && "text-muted-foreground",
                    )}
                    aria-live="polite"
                  >
                    {status.tone === "warning" || status.tone === "danger" ? (
                      <AlertTriangle className="size-4 shrink-0" aria-hidden="true" />
                    ) : status.tone === "success" ? (
                      <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />
                    ) : (
                      <Info className="size-4 shrink-0" aria-hidden="true" />
                    )}
                    {status.text}
                  </p>
                  <div className="flex gap-2">
                    <Button variant="secondary" onClick={runPreview} loading={busy === "preview"} disabled={!built.operation || busy !== null || pending !== null}>
                      {busy !== "preview" && <Eye />} Preview
                    </Button>
                    <Button
                      variant={preview?.result.destructive ? "danger" : "primary"}
                      onClick={() => (preview?.result.destructive ? setConfirmOpen(true) : void apply())}
                      loading={busy === "apply"}
                      disabled={!canApply || busy !== null || pending !== null}
                    >
                      {busy !== "apply" && <Check />} Apply
                    </Button>
                  </div>
                </div>
                {opError && (
                  <div className="border-t border-border px-5 py-4">
                    <Alert
                      tone="danger"
                      title={opError.stage === "preview" ? "Preview failed" : "The operation was not applied"}
                      action={
                        <Button size="sm" variant="secondary" onClick={() => void runPreview()} disabled={!built.operation || busy !== null}>
                          {opError.error.code === "preview_outdated" || opError.error.code === "preview_required" ? "Preview again" : "Try again"}
                        </Button>
                      }
                    >
                      {opError.error.message} {opError.error.hint}
                      {opError.stage === "apply" && <> Your data was not changed.</>}
                    </Alert>
                  </div>
                )}
              </>
            )}
          </Card>

          {preview && previewIsCurrent && (
            <Card>
              <CardHeader>
                <CardTitle>Proposed changes</CardTitle>
                <CardDescription>Calculated on the full dataset. Nothing has been changed yet.</CardDescription>
              </CardHeader>
              <CardContent>
                <PreviewResult preview={preview.result} mode="preview" />
              </CardContent>
            </Card>
          )}

          {lastApplied && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <CheckCircle2 className="size-4 text-success" aria-hidden="true" /> Result
                </CardTitle>
                <CardDescription>The working data has been updated. Use Undo in the top bar to reverse this step.</CardDescription>
              </CardHeader>
              <CardContent>
                <PreviewResult preview={lastApplied} mode="applied" />
              </CardContent>
            </Card>
          )}

          <div className="lg:hidden">
            <CleaningHistory />
          </div>
        </div>
      </div>

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Remove data from the working dataset?"
        description={preview ? `If applied: ${preview.result.summary}` : undefined}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => void apply()}>
              Yes, apply
            </Button>
          </>
        }
      >
        <p className="text-body text-slate-700">
          {preview && preview.result.rows_removed > 0 && <>{pluralize(preview.result.rows_removed, "row")} will be removed. </>}
          {preview && preview.result.columns_removed > 0 && <>{pluralize(preview.result.columns_removed, "column")} will be removed. </>}
          Your original upload is not affected, and you can undo this step afterwards.
        </p>
      </Dialog>
    </div>
  );
}
