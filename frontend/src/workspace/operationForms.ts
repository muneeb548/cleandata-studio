/**
 * Pure helpers that turn the cleaning form state into an API operation.
 * Kept free of React so they are easy to unit test.
 */
import type { ColumnProfile, FlagRule, JoinHow, JoinKey, Operation, OperationType, SortKey } from "@/api/types";

/** "mark_missing" is a shortcut that builds a map_values operation (listed words → empty). */
export type CleanChoice = OperationType | "outliers" | "mark_missing";

export type FormState = {
  keep: "first" | "last";
  mvStrategy: "drop_rows" | "drop_columns" | "fill_mean" | "fill_median" | "fill_constant";
  mvColumns: string[];
  mvValue: string;
  trimAll: boolean;
  trimColumns: string[];
  caseColumns: string[];
  caseMode: "lower" | "upper" | "title";
  replaceSpaces: boolean;
  lowercase: boolean;
  convColumns: string[];
  convTarget: "integer" | "float" | "string" | "datetime";
  convOnError: "abort" | "set_missing";
  convFormat: string;
  convDayfirst: boolean;
  emptyTarget: "rows" | "columns" | "both";
  frColumns: string[];
  frFind: string;
  frReplace: string;
  frMatch: "exact" | "contains";
  frCaseSensitive: boolean;
  outlierColumn: string;
  splitColumn: string;
  splitSeparator: string;
  splitNames: string[];
  splitFrom: "start" | "end";
  splitKeep: boolean;
  mergeColumns: string[];
  mergeSeparator: string;
  mergeName: string;
  mergeKeep: boolean;
  phoneColumns: string[];
  phoneRegion: string;
  phoneRegionSource: "fixed" | "column";
  phoneRegionColumn: string;
  phoneFormat: "national" | "international" | "e164";
  phoneOnInvalid: "keep" | "set_missing";
  flagRules: FlagRule[];
  flagColumnName: string;
  flagRegion: string;
  flagRegionColumn: string;
  countryColumns: string[];
  countryOutput: "name" | "code";
  emailColumns: string[];
  emailLowercase: boolean;
  emailFixDomains: boolean;
  emailOnInvalid: "keep" | "set_missing";
  numColumns: string[];
  numDecimal: "auto" | "." | ",";
  numOnError: "abort" | "set_missing";
  mapColumn: string;
  mapEdits: Record<string, string>;
  mapIgnoreCase: boolean;
  ndColumns: string[];
  ndMatch: "normalized" | "similar";
  ndAction: "flag" | "remove";
  ndColumnName: string;
  /** organize_columns: every column in the order it should have (current names) */
  orgOrder: string[];
  orgRenames: Record<string, string>;
  orgDrop: string[];
  sortKeys: SortKey[];
  sortMissing: "last" | "first";
  mmColumns: string[];
  mmWords: string;
  /** combine_files: the added file to combine with, and how */
  cfFileId: string;
  cfMode: "append" | "join";
  cfSourceOn: boolean;
  cfSourceName: string;
  cfKeys: JoinKey[];
  cfHow: JoinHow;
  cfLoose: boolean;
  cfDuplicates: "first" | "all";
  /** columns to bring from the other file (empty = all except the match columns) */
  cfColumns: string[];
};

export const DEFAULT_FORM: FormState = {
  keep: "first",
  mvStrategy: "fill_constant",
  mvColumns: [],
  mvValue: "",
  trimAll: true,
  trimColumns: [],
  caseColumns: [],
  caseMode: "title",
  replaceSpaces: true,
  lowercase: true,
  convColumns: [],
  convTarget: "integer",
  convOnError: "abort",
  convFormat: "",
  convDayfirst: false,
  emptyTarget: "both",
  frColumns: [],
  frFind: "",
  frReplace: "",
  frMatch: "exact",
  frCaseSensitive: false,
  outlierColumn: "",
  splitColumn: "",
  splitSeparator: " ",
  splitNames: ["first_name", "last_name"],
  splitFrom: "start",
  splitKeep: true,
  mergeColumns: [],
  mergeSeparator: " ",
  mergeName: "",
  mergeKeep: true,
  phoneColumns: [],
  phoneRegion: "US",
  phoneRegionSource: "fixed",
  phoneRegionColumn: "",
  phoneFormat: "international",
  phoneOnInvalid: "keep",
  flagRules: [],
  flagColumnName: "needs_review",
  flagRegion: "",
  flagRegionColumn: "",
  countryColumns: [],
  countryOutput: "name",
  emailColumns: [],
  emailLowercase: true,
  emailFixDomains: false,
  emailOnInvalid: "keep",
  numColumns: [],
  numDecimal: "auto",
  numOnError: "abort",
  mapColumn: "",
  mapEdits: {},
  mapIgnoreCase: true,
  ndColumns: [],
  ndMatch: "normalized",
  ndAction: "flag",
  ndColumnName: "duplicate_group",
  orgOrder: [],
  orgRenames: {},
  orgDrop: [],
  sortKeys: [{ column: "", direction: "asc" }],
  sortMissing: "last",
  mmColumns: [],
  mmWords: "Unknown, unk, TBD, not known, ---",
  cfFileId: "",
  cfMode: "append",
  cfSourceOn: false,
  cfSourceName: "source_file",
  cfKeys: [{ left: "", right: "" }],
  cfHow: "left",
  cfLoose: true,
  cfDuplicates: "first",
  cfColumns: [],
};

/** Words typed in the "mark as missing" box, split on commas or new lines. */
export function missingWords(text: string): string[] {
  return [...new Set(text.split(/[,\n]/).map((w) => w.trim()).filter(Boolean))];
}

/** Rows of the mapping table that actually change something. */
export function mappingRows(edits: Record<string, string>): { value: string; to: string }[] {
  return Object.entries(edits)
    .filter(([value, to]) => to.trim() !== "" && to.trim() !== value)
    .map(([value, to]) => ({ value, to: to.trim() }));
}

/** Countries offered for phone numbers written without a + country code (any other code can be typed). */
export const PHONE_REGIONS = [
  "US", "GB", "CA", "AU", "NZ", "IE", "DE", "FR", "ES", "IT", "NL", "BE", "CH", "AT", "SE", "NO", "DK", "FI",
  "PL", "PT", "GR", "CZ", "RO", "HU", "TR", "AE", "SA", "QA", "KW", "OM", "BH", "EG", "ZA", "NG", "KE", "IN",
  "PK", "BD", "LK", "NP", "CN", "JP", "KR", "SG", "MY", "ID", "PH", "TH", "VN", "HK", "BR", "MX", "AR", "CL",
  "CO", "PE", "IL", "UA",
] as const;

export const FLAG_CHECKS: { value: FlagRule["check"]; label: string }[] = [
  { value: "missing", label: "Missing value" },
  { value: "invalid_email", label: "Invalid email" },
  { value: "invalid_phone", label: "Invalid phone number" },
  { value: "not_number", label: "Not a number" },
  { value: "not_date", label: "Not a date" },
  { value: "duplicate_value", label: "Repeated value (e.g. same email twice)" },
  { value: "out_of_range", label: "Outside an allowed range (e.g. age 0–100)" },
];

export const isNumeric = (c: Pick<ColumnProfile, "type">) => c.type === "integer" || c.type === "decimal";

/** Why a column cannot be used for a given choice (null = eligible). */
export function columnRestriction(choice: CleanChoice, form: FormState, col: ColumnProfile): string | null {
  switch (choice) {
    case "missing_values":
      if ((form.mvStrategy === "fill_mean" || form.mvStrategy === "fill_median") && !isNumeric(col)) return "Not numeric";
      return null;
    case "trim_whitespace":
    case "standardize_text":
    case "find_replace":
    case "split_column":
    case "standardize_country":
    case "clean_email":
    case "map_values":
    case "mark_missing":
      return col.is_text ? null : "Not text";
    default:
      return null;
  }
}

export type BuildResult = { operation: Operation; error?: undefined } | { operation?: undefined; error: string };

export function buildOperation(choice: CleanChoice, f: FormState): BuildResult {
  const needColumns = (cols: string[]) => (cols.length ? null : "Select at least one column.");
  switch (choice) {
    case "remove_duplicates":
      return { operation: { type: "remove_duplicates", keep: f.keep } };
    case "missing_values": {
      const err = needColumns(f.mvColumns);
      if (err) return { error: err };
      if (f.mvStrategy === "fill_constant" && f.mvValue === "") return { error: "Enter the value to fill missing cells with." };
      return {
        operation: {
          type: "missing_values",
          strategy: f.mvStrategy,
          columns: f.mvColumns,
          ...(f.mvStrategy === "fill_constant" ? { value: f.mvValue } : {}),
        },
      };
    }
    case "trim_whitespace":
      if (!f.trimAll && !f.trimColumns.length) return { error: "Select at least one column, or apply to all text columns." };
      return { operation: { type: "trim_whitespace", columns: f.trimAll ? [] : f.trimColumns } };
    case "standardize_text":
      return needColumns(f.caseColumns)
        ? { error: "Select at least one column." }
        : { operation: { type: "standardize_text", columns: f.caseColumns, case: f.caseMode } };
    case "clean_column_names":
      return { operation: { type: "clean_column_names", replace_spaces: f.replaceSpaces, lowercase: f.lowercase } };
    case "convert_type":
      return needColumns(f.convColumns)
        ? { error: "Select at least one column." }
        : {
            operation: {
              type: "convert_type",
              columns: f.convColumns,
              target: f.convTarget,
              on_error: f.convOnError,
              date_format: f.convTarget === "datetime" && f.convFormat.trim() ? f.convFormat.trim() : null,
              dayfirst: f.convTarget === "datetime" ? f.convDayfirst : false,
            },
          };
    case "remove_empty":
      return { operation: { type: "remove_empty", target: f.emptyTarget } };
    case "find_replace":
      if (!f.frColumns.length) return { error: "Select at least one column." };
      if (!f.frFind) return { error: "Enter the text to find." };
      return {
        operation: {
          type: "find_replace",
          columns: f.frColumns,
          find: f.frFind,
          replace: f.frReplace,
          match: f.frMatch,
          case_sensitive: f.frCaseSensitive,
        },
      };
    case "split_column": {
      if (!f.splitColumn) return { error: "Choose the column to split." };
      if (!f.splitSeparator) return { error: "Enter the separator between the parts." };
      const names = f.splitNames.map((n) => n.trim());
      if (names.length < 2 || names.some((n) => !n)) return { error: "Give every new column a name." };
      if (new Set(names).size !== names.length) return { error: "The new column names must be different." };
      return {
        operation: {
          type: "split_column",
          column: f.splitColumn,
          separator: f.splitSeparator,
          names,
          split_from: f.splitFrom,
          keep_original: f.splitKeep,
        },
      };
    }
    case "merge_columns":
      if (f.mergeColumns.length < 2) return { error: "Select at least two columns to merge." };
      if (!f.mergeName.trim()) return { error: "Enter a name for the new column." };
      return {
        operation: {
          type: "merge_columns",
          columns: f.mergeColumns,
          separator: f.mergeSeparator,
          new_name: f.mergeName.trim(),
          keep_originals: f.mergeKeep,
        },
      };
    case "standardize_phone":
      if (!f.phoneColumns.length) return { error: "Select at least one column." };
      if (!/^[A-Za-z]{2}$/.test(f.phoneRegion)) return { error: "Choose the country of numbers written without a + code." };
      if (f.phoneRegionSource === "column" && !f.phoneRegionColumn) return { error: "Choose the column that holds each row's country." };
      if (f.phoneRegionSource === "column" && f.phoneColumns.includes(f.phoneRegionColumn))
        return { error: "The country column cannot also be a phone column." };
      return {
        operation: {
          type: "standardize_phone",
          columns: f.phoneColumns,
          region: f.phoneRegion.toUpperCase(),
          region_column: f.phoneRegionSource === "column" ? f.phoneRegionColumn : null,
          format: f.phoneFormat,
          on_invalid: f.phoneOnInvalid,
        },
      };
    case "flag_rows": {
      if (!f.flagRules.length) return { error: "Add at least one check." };
      if (!f.flagColumnName.trim()) return { error: "Enter a name for the review column." };
      const region = /^[A-Za-z]{2}$/.test(f.flagRegion) ? f.flagRegion.toUpperCase() : null;
      const region_column = f.flagRegionColumn || null;
      return {
        operation: {
          type: "flag_rows",
          rules: f.flagRules.map((r) =>
            r.check === "invalid_phone"
              ? { column: r.column, check: r.check, region, region_column }
              : r.check === "out_of_range"
                ? { column: r.column, check: r.check, min: r.min?.trim() || null, max: r.max?.trim() || null }
                : { column: r.column, check: r.check },
          ),
          column_name: f.flagColumnName.trim(),
        },
      };
    }
    case "clean_email":
      return f.emailColumns.length
        ? {
            operation: {
              type: "clean_email",
              columns: f.emailColumns,
              lowercase: f.emailLowercase,
              fix_domains: f.emailFixDomains,
              on_invalid: f.emailOnInvalid,
            },
          }
        : { error: "Select at least one column." };
    case "clean_numbers":
      return f.numColumns.length
        ? { operation: { type: "clean_numbers", columns: f.numColumns, decimal: f.numDecimal, on_error: f.numOnError } }
        : { error: "Select at least one column." };
    case "near_duplicates":
      if (!f.ndColumns.length) return { error: "Select the columns that identify a record, e.g. name and email." };
      if (f.ndAction === "flag" && !f.ndColumnName.trim()) return { error: "Enter a name for the group column." };
      return {
        operation: {
          type: "near_duplicates",
          columns: f.ndColumns,
          match: f.ndMatch,
          action: f.ndAction,
          column_name: f.ndColumnName.trim() || "duplicate_group",
        },
      };
    case "map_values": {
      if (!f.mapColumn) return { error: "Choose a column." };
      const mappings = mappingRows(f.mapEdits);
      if (!mappings.length) return { error: "Type a new value next to at least one value." };
      return { operation: { type: "map_values", columns: [f.mapColumn], mappings, ignore_case: f.mapIgnoreCase } };
    }
    case "standardize_country":
      return f.countryColumns.length
        ? { operation: { type: "standardize_country", columns: f.countryColumns, output: f.countryOutput } }
        : { error: "Select at least one column." };
    case "organize_columns": {
      const drop = f.orgDrop;
      const rename = f.orgOrder
        .filter((c) => !drop.includes(c))
        .map((c) => ({ column: c, to: (f.orgRenames[c] ?? "").trim() }))
        .filter((r) => r.to && r.to !== r.column);
      const finalNames = f.orgOrder.filter((c) => !drop.includes(c)).map((c) => (f.orgRenames[c] ?? "").trim() || c);
      if (f.orgOrder.length && drop.length === f.orgOrder.length) return { error: "Keep at least one column." };
      const dup = finalNames.find((n, i) => finalNames.indexOf(n) !== i);
      if (dup) return { error: `Two columns would be called “${dup}”. Choose different names.` };
      return { operation: { type: "organize_columns", rename, drop, order: f.orgOrder.filter((c) => !drop.includes(c)) } };
    }
    case "sort_rows": {
      const by = f.sortKeys.filter((k) => k.column);
      if (!by.length) return { error: "Choose a column to sort by." };
      if (new Set(by.map((k) => k.column)).size !== by.length) return { error: "Use each column only once." };
      return { operation: { type: "sort_rows", by, missing: f.sortMissing } };
    }
    case "mark_missing": {
      if (!f.mmColumns.length) return { error: "Select at least one column." };
      const words = missingWords(f.mmWords);
      if (!words.length) return { error: "Type the words that mean “no value”, separated by commas." };
      return {
        operation: { type: "map_values", columns: f.mmColumns, mappings: words.map((w) => ({ value: w, to: "" })), ignore_case: true },
      };
    }
    case "combine_files": {
      if (!f.cfFileId) return { error: "Add the other file, then choose it." };
      if (f.cfMode === "append") {
        if (f.cfSourceOn && !f.cfSourceName.trim()) return { error: "Enter a name for the column that records the source file." };
        return {
          operation: { type: "combine_files", file_id: f.cfFileId, mode: "append", source_column: f.cfSourceOn ? f.cfSourceName.trim() : null },
        };
      }
      const keys = f.cfKeys.filter((k) => k.left || k.right);
      if (!keys.length || keys.some((k) => !k.left || !k.right)) return { error: "Choose the matching column in both files." };
      if (new Set(keys.map((k) => k.left)).size !== keys.length || new Set(keys.map((k) => k.right)).size !== keys.length)
        return { error: "Use each column only once to match rows." };
      return {
        operation: {
          type: "combine_files",
          file_id: f.cfFileId,
          mode: "join",
          keys,
          how: f.cfHow,
          loose_keys: f.cfLoose,
          duplicates: f.cfDuplicates,
          columns: f.cfColumns.filter((c) => !keys.some((k) => k.right === c)),
        },
      };
    }
    case "outliers":
      return { error: "Outlier review does not change data." };
  }
}

/** Columns that probably hold the same thing in both files (same name ignoring case, spaces and _ or -). */
export function suggestJoinKey(current: string[], other: string[]): JoinKey | null {
  const norm = (s: string) => s.toLowerCase().replace(/[\s_-]+/g, "");
  const preferred = ["email", "emailaddress", "id", "customerid", "orderid", "phone", "sku", "code"];
  const pairs: JoinKey[] = [];
  for (const left of current) {
    const right = other.find((o) => norm(o) === norm(left));
    if (right) pairs.push({ left, right });
  }
  if (!pairs.length) return null;
  return pairs.find((p) => preferred.includes(norm(p.left))) ?? pairs[0];
}

/** Pre-fill the form when the user clicks "Fix" on a detected issue. */
export function formForIssue(choice: CleanChoice, column: string | null | undefined, issueId: string | undefined, columns: ColumnProfile[], base: FormState, example?: string | null): FormState {
  const col = columns.find((c) => c.name === column);
  const f = { ...base };
  const one = column && col ? [column] : [];
  switch (choice) {
    case "missing_values":
      f.mvColumns = one;
      f.mvStrategy = col && isNumeric(col) ? "fill_median" : "fill_constant";
      break;
    case "trim_whitespace":
      f.trimAll = !one.length;
      f.trimColumns = one;
      break;
    case "standardize_text":
      f.caseColumns = one;
      break;
    case "find_replace":
      f.frColumns = one;
      // Prefill with a real value reported by the server, never a guessed one.
      f.frFind = example ?? "";
      f.frReplace = "";
      f.frMatch = "exact";
      f.frCaseSensitive = false;
      break;
    case "convert_type":
      f.convColumns = one;
      f.convTarget = issueId?.startsWith("dates:") ? "datetime" : "float";
      f.convOnError = "abort";
      break;
    case "remove_empty":
      f.emptyTarget = issueId?.startsWith("empty_col:") ? "columns" : issueId === "empty_rows" ? "rows" : "both";
      break;
    case "outliers":
      f.outlierColumn = column ?? "";
      break;
    case "clean_email":
      f.emailColumns = one;
      break;
    case "standardize_phone": {
      f.phoneColumns = one;
      // Mixed countries are best read from a country column when the file has one.
      const country = columns.find((c) => /countr|nation/i.test(c.name) && c.name !== column);
      f.phoneRegionSource = country ? "column" : "fixed";
      f.phoneRegionColumn = country?.name ?? "";
      break;
    }
    case "standardize_country":
      f.countryColumns = one;
      break;
    case "clean_numbers":
      f.numColumns = one;
      break;
  }
  return f;
}

export const CHOICES: { id: CleanChoice; label: string; description: string }[] = [
  { id: "remove_duplicates", label: "Remove duplicate rows", description: "Delete exact copies of earlier rows." },
  { id: "near_duplicates", label: "Find near-duplicates", description: "Same record written slightly differently." },
  { id: "missing_values", label: "Handle missing values", description: "Drop or fill empty cells in selected columns." },
  { id: "trim_whitespace", label: "Trim whitespace", description: "Remove leading and trailing spaces." },
  { id: "standardize_text", label: "Standardize text case", description: "lowercase, UPPERCASE or Title Case." },
  { id: "clean_column_names", label: "Clean column names", description: "Trim, underscores, unique names." },
  { id: "organize_columns", label: "Organize columns", description: "Rename, remove and reorder columns." },
  { id: "sort_rows", label: "Sort rows", description: "Numbers, dates or text; the download keeps the order." },
  { id: "mark_missing", label: "Mark words as missing", description: "“Unknown”, “TBD” … become empty cells." },
  { id: "convert_type", label: "Convert data type", description: "Integer, decimal, text or date." },
  { id: "remove_empty", label: "Remove empty rows/columns", description: "Drop rows or columns with no values." },
  { id: "find_replace", label: "Find and replace", description: "Replace values in selected columns." },
  { id: "outliers", label: "Review outliers", description: "IQR check for numeric columns. Read-only." },
  { id: "split_column", label: "Split column", description: "One column into several, e.g. first and last name." },
  { id: "merge_columns", label: "Merge columns", description: "Several columns into one new column." },
  { id: "standardize_phone", label: "Standardize phone numbers", description: "One format for numbers from any country." },
  { id: "standardize_country", label: "Standardize country names", description: "USA, U.S.A., america → United States." },
  { id: "clean_email", label: "Clean email addresses", description: "Spaces, capitals, mailto: and invalid emails." },
  { id: "clean_numbers", label: "Clean numbers and currencies", description: "$1,250.00, Rs 1,25,000, 1.234,56 € → numbers." },
  { id: "map_values", label: "Map values", description: "Replace many values at once from a table." },
  { id: "flag_rows", label: "Flag rows for review", description: "Add a column explaining which rows need attention." },
  { id: "combine_files", label: "Combine files", description: "Add rows or columns from another file (like VLOOKUP)." },
];

export type CategoryId =
  | "duplicates"
  | "missing"
  | "text"
  | "columns"
  | "types"
  | "outliers"
  | "empty"
  | "replace"
  | "split"
  | "phone"
  | "flags"
  | "combine";

/** Operations grouped the way users think about cleaning. */
export const CATEGORIES: { id: CategoryId; label: string; description: string; choices: CleanChoice[] }[] = [
  { id: "duplicates", label: "Duplicates", description: "Exact and near-duplicates", choices: ["remove_duplicates", "near_duplicates"] },
  { id: "missing", label: "Missing values", description: "Fill, remove or mark empty cells", choices: ["missing_values", "mark_missing"] },
  { id: "text", label: "Text cleaning", description: "Spaces and capitalisation", choices: ["trim_whitespace", "standardize_text"] },
  { id: "columns", label: "Columns & sorting", description: "Rename, remove, reorder, sort", choices: ["organize_columns", "sort_rows", "clean_column_names"] },
  { id: "types", label: "Data types", description: "Numbers, dates, currencies", choices: ["convert_type", "clean_numbers"] },
  { id: "outliers", label: "Outliers", description: "Review unusual numbers", choices: ["outliers"] },
  { id: "empty", label: "Empty rows & columns", description: "Drop fully empty rows or columns", choices: ["remove_empty"] },
  { id: "replace", label: "Find & replace", description: "Change one or many values", choices: ["find_replace", "map_values"] },
  { id: "split", label: "Split & merge", description: "Split or join columns", choices: ["split_column", "merge_columns"] },
  { id: "phone", label: "Contact details", description: "Phones, emails, countries", choices: ["standardize_phone", "clean_email", "standardize_country"] },
  { id: "flags", label: "Flag for review", description: "Mark rows that need checking", choices: ["flag_rows"] },
  { id: "combine", label: "Combine files", description: "Stack files or match rows (VLOOKUP)", choices: ["combine_files"] },
];

export function categoryOf(choice: CleanChoice): CategoryId {
  return CATEGORIES.find((c) => c.choices.includes(choice))!.id;
}
