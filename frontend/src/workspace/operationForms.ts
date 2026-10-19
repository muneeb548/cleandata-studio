/**
 * Pure helpers that turn the cleaning form state into an API operation.
 * Kept free of React so they are easy to unit test.
 */
import type { ColumnProfile, FlagRule, Operation, OperationType } from "@/api/types";

export type CleanChoice = OperationType | "outliers";

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
};

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
            r.check === "invalid_phone" ? { column: r.column, check: r.check, region, region_column } : { column: r.column, check: r.check },
          ),
          column_name: f.flagColumnName.trim(),
        },
      };
    }
    case "standardize_country":
      return f.countryColumns.length
        ? { operation: { type: "standardize_country", columns: f.countryColumns, output: f.countryOutput } }
        : { error: "Select at least one column." };
    case "outliers":
      return { error: "Outlier review does not change data." };
  }
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
  }
  return f;
}

export const CHOICES: { id: CleanChoice; label: string; description: string }[] = [
  { id: "remove_duplicates", label: "Remove duplicate rows", description: "Delete exact copies of earlier rows." },
  { id: "missing_values", label: "Handle missing values", description: "Drop or fill empty cells in selected columns." },
  { id: "trim_whitespace", label: "Trim whitespace", description: "Remove leading and trailing spaces." },
  { id: "standardize_text", label: "Standardize text case", description: "lowercase, UPPERCASE or Title Case." },
  { id: "clean_column_names", label: "Clean column names", description: "Trim, underscores, unique names." },
  { id: "convert_type", label: "Convert data type", description: "Integer, decimal, text or date." },
  { id: "remove_empty", label: "Remove empty rows/columns", description: "Drop rows or columns with no values." },
  { id: "find_replace", label: "Find and replace", description: "Replace values in selected columns." },
  { id: "outliers", label: "Review outliers", description: "IQR check for numeric columns. Read-only." },
  { id: "split_column", label: "Split column", description: "One column into several, e.g. first and last name." },
  { id: "merge_columns", label: "Merge columns", description: "Several columns into one new column." },
  { id: "standardize_phone", label: "Standardize phone numbers", description: "One format for numbers from any country." },
  { id: "standardize_country", label: "Standardize country names", description: "USA, U.S.A., america → United States." },
  { id: "flag_rows", label: "Flag rows for review", description: "Add a column explaining which rows need attention." },
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
  | "flags";

/** Operations grouped the way users think about cleaning. */
export const CATEGORIES: { id: CategoryId; label: string; description: string; choices: CleanChoice[] }[] = [
  { id: "duplicates", label: "Duplicates", description: "Remove repeated rows", choices: ["remove_duplicates"] },
  { id: "missing", label: "Missing values", description: "Fill or remove empty cells", choices: ["missing_values"] },
  { id: "text", label: "Text cleaning", description: "Spaces and capitalisation", choices: ["trim_whitespace", "standardize_text"] },
  { id: "columns", label: "Column names", description: "Tidy and de-duplicate headers", choices: ["clean_column_names"] },
  { id: "types", label: "Data types", description: "Numbers, dates or text", choices: ["convert_type"] },
  { id: "outliers", label: "Outliers", description: "Review unusual numbers", choices: ["outliers"] },
  { id: "empty", label: "Empty rows & columns", description: "Drop fully empty rows or columns", choices: ["remove_empty"] },
  { id: "replace", label: "Find & replace", description: "Change specific values", choices: ["find_replace"] },
  { id: "split", label: "Split & merge", description: "Split or join columns", choices: ["split_column", "merge_columns"] },
  { id: "phone", label: "Phones & countries", description: "One format, any country", choices: ["standardize_phone", "standardize_country"] },
  { id: "flags", label: "Flag for review", description: "Mark rows that need checking", choices: ["flag_rows"] },
];

export function categoryOf(choice: CleanChoice): CategoryId {
  return CATEGORIES.find((c) => c.choices.includes(choice))!.id;
}
