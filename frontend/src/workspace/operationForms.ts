/**
 * Pure helpers that turn the cleaning form state into an API operation.
 * Kept free of React so they are easy to unit test.
 */
import type { ColumnProfile, Operation, OperationType } from "@/api/types";

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
};

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
];

export type CategoryId = "duplicates" | "missing" | "text" | "columns" | "types" | "outliers" | "empty" | "replace";

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
];

export function categoryOf(choice: CleanChoice): CategoryId {
  return CATEGORIES.find((c) => c.choices.includes(choice))!.id;
}
