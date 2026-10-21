/** Types mirroring the FastAPI responses. Keep in sync with backend/app/services/workspace.py. */

export type CellValue = string | number | boolean | null;
export type ColumnType = "integer" | "decimal" | "text" | "datetime" | "boolean" | "empty";
export type DatasetKind = "original" | "current";

export type ImportFormat = "csv" | "tsv" | "xlsx" | "xls" | "json";
export type ExportFormat = "csv" | "xlsx";

export interface FileInfo {
  name: string;
  size: number;
  encoding: string | null;
  delimiter: string | null;
  format: ImportFormat;
  format_label: string;
  sheet: string | null;
  sheets: string[];
  warnings: string[];
}

export interface Shape {
  rows: number;
  columns: number;
}

export interface HistoryItem {
  id: string;
  type: OperationType;
  label: string;
  params: Record<string, unknown>;
  summary: string;
  applied_at: number;
  rows_before: number;
  rows_after: number;
  columns_before: number;
  columns_after: number;
  rows_removed: number;
  columns_removed: number;
  cells_changed: number;
  warnings: string[];
  /** False once the snapshot was dropped to save memory (the step stays in the log). */
  undoable: boolean;
}

export interface SessionInfo {
  file: FileInfo;
  original_shape: Shape;
  current_shape: Shape;
  history: HistoryItem[];
  log: LogEvent[];
  can_undo: boolean;
  expires_in_seconds: number;
}

export interface LogEvent {
  event: "applied" | "undone" | "reset";
  at: number;
  step_id: string | null;
  type: OperationType | null;
  label: string | null;
  summary: string | null;
}

export interface HistoryResponse {
  steps: HistoryItem[];
  log: LogEvent[];
  can_undo: boolean;
}

export interface UploadResponse extends SessionInfo {
  session_id: string;
}

export interface Stats {
  rows: number;
  columns: number;
  total_cells: number;
  missing_cells: number;
  duplicate_rows: number;
  columns_with_missing: number;
  completeness: number | null;
  empty_rows: number;
  empty_columns: number;
}

export interface ColumnProfile {
  name: string;
  type: ColumnType;
  missing: number;
  /** null when the dataset has no rows */
  missing_pct: number | null;
  completeness: number | null;
  /** Not calculated in the light profile used by the cleaning forms. */
  unique: number | null;
  /** Values are stored as text, so text operations (trim, case, find & replace) are allowed. */
  is_text: boolean;
  min?: CellValue;
  max?: CellValue;
  mean?: CellValue;
  median?: CellValue;
  /** cells holding "N/A", "null"… or only spaces (full profile only) */
  looks_empty?: number;
  /** detected problems in this column (full profile only) */
  issues?: number;
}

export interface Health {
  looks_empty_cells: number;
  /** completeness when placeholder and space-only cells also count as missing */
  real_completeness: number | null;
  /** problems found (notes to review not included) */
  issues: number;
  /** findings that are only worth a look */
  notes: number;
  columns_with_issues: number;
  needs_cleaning: boolean;
}

export type Severity = "high" | "medium" | "low" | "info";

export interface Issue {
  id: string;
  severity: Severity;
  title: string;
  description: string;
  column: string | null;
  count: number | null;
  suggested_operation: OperationType | "outliers" | null;
  /** One affected value, when the issue is about specific values (e.g. a placeholder). */
  example?: string | null;
}

export interface Profile {
  dataset: DatasetKind;
  stats: Stats;
  columns: ColumnProfile[];
  type_distribution: Partial<Record<ColumnType, number>>;
  issues: Issue[];
  /** not calculated in the light profile */
  health?: Health | null;
}

export interface RowsPage {
  dataset: DatasetKind;
  columns: { name: string; type: ColumnType }[];
  rows: CellValue[][];
  row_numbers: number[];
  page: number;
  page_size: number;
  total_rows: number;
  unfiltered_rows: number;
  total_pages: number;
}

export type OperationType =
  | "remove_duplicates"
  | "missing_values"
  | "trim_whitespace"
  | "standardize_text"
  | "clean_column_names"
  | "convert_type"
  | "remove_empty"
  | "find_replace"
  | "split_column"
  | "merge_columns"
  | "standardize_phone"
  | "standardize_country"
  | "clean_email"
  | "clean_numbers"
  | "map_values"
  | "near_duplicates"
  | "flag_rows"
  | "organize_columns"
  | "sort_rows";

export interface QuickStep {
  id: string;
  title: string;
  label: string;
  summary: string;
  operation: Operation;
  selected: boolean;
  note: string | null;
  warnings: string[];
}

export interface QuickCleanPlan {
  steps: QuickStep[];
  needs_decision: string[];
}

export interface QuickCleanPreview {
  steps: { label: string; summary: string; changed: boolean; blocked: string | null; warnings: string[] }[];
  rows_before: number;
  rows_after: number;
  columns_before: number;
  columns_after: number;
  cells_changed: number;
  blocked: string | null;
  preview_token: string;
}

export interface QuickCleanResult {
  steps: { label: string; summary: string; applied: boolean }[];
  applied: number;
  session: SessionInfo;
}

export interface Recipe {
  app: "CleanData Studio";
  kind: "cleaning-recipe";
  version: number;
  name: string;
  source_file: string;
  created_at: string;
  steps: Operation[];
}

export interface ChangeReport {
  file: string;
  rows_before: number;
  rows_after: number;
  columns_before: number;
  columns_after: number;
  steps: { label: string; summary: string }[];
  review: { column: string; rows: number }[];
  open_items: string[];
  message: string;
}

export interface ColumnValues {
  column: string;
  distinct: number;
  values: { value: string; count: number }[];
  truncated: boolean;
}

export type FlagCheck = "missing" | "invalid_email" | "invalid_phone" | "not_number" | "not_date" | "duplicate_value" | "out_of_range";
export type FlagRule = {
  column: string;
  check: FlagCheck;
  region?: string | null;
  region_column?: string | null;
  /** out_of_range only: smallest / largest allowed value (a number or a date) */
  min?: string | null;
  max?: string | null;
};
export type SortKey = { column: string; direction: "asc" | "desc" };

export type Operation =
  | { type: "remove_duplicates"; keep: "first" | "last" }
  | {
      type: "missing_values";
      strategy: "drop_rows" | "drop_columns" | "fill_mean" | "fill_median" | "fill_constant";
      columns: string[];
      value?: string;
    }
  | { type: "trim_whitespace"; columns: string[] }
  | { type: "standardize_text"; columns: string[]; case: "lower" | "upper" | "title" }
  | { type: "clean_column_names"; replace_spaces: boolean; lowercase: boolean }
  | {
      type: "convert_type";
      columns: string[];
      target: "integer" | "float" | "string" | "datetime";
      on_error: "set_missing" | "abort";
      date_format?: string | null;
      dayfirst?: boolean;
    }
  | { type: "remove_empty"; target: "rows" | "columns" | "both" }
  | {
      type: "find_replace";
      columns: string[];
      find: string;
      replace: string;
      match: "exact" | "contains";
      case_sensitive: boolean;
    }
  | {
      type: "split_column";
      column: string;
      separator: string;
      names: string[];
      split_from: "start" | "end";
      keep_original: boolean;
    }
  | { type: "merge_columns"; columns: string[]; separator: string; new_name: string; keep_originals: boolean }
  | {
      type: "standardize_phone";
      columns: string[];
      region: string;
      region_column: string | null;
      format: "national" | "international" | "e164";
      on_invalid: "keep" | "set_missing";
    }
  | { type: "standardize_country"; columns: string[]; output: "name" | "code" }
  | { type: "clean_email"; columns: string[]; lowercase: boolean; fix_domains: boolean; on_invalid: "keep" | "set_missing" }
  | { type: "clean_numbers"; columns: string[]; decimal: "auto" | "." | ","; on_error: "abort" | "set_missing" }
  | { type: "map_values"; columns: string[]; mappings: { value: string; to: string }[]; ignore_case: boolean }
  | { type: "near_duplicates"; columns: string[]; match: "normalized" | "similar"; action: "flag" | "remove"; column_name: string }
  | { type: "flag_rows"; rules: FlagRule[]; column_name: string }
  | { type: "organize_columns"; rename: { column: string; to: string }[]; drop: string[]; order: string[] }
  | { type: "sort_rows"; by: SortKey[]; missing: "last" | "first" };

export interface CellChange {
  row: number;
  column: string;
  before: CellValue;
  after: CellValue;
}

export interface OperationPreview {
  operation: { type: OperationType; label: string; params: Record<string, unknown> };
  summary: string;
  warnings: string[];
  blocked: string | null;
  destructive: boolean;
  changed: boolean;
  rows_before: number;
  rows_after: number;
  columns_before: number;
  columns_after: number;
  rows_removed: number;
  columns_removed: number;
  cells_changed: number;
  changes: {
    cell_samples: CellChange[];
    removed_rows: { columns: string[]; row_numbers: number[]; rows: CellValue[][] } | null;
    removed_columns: string[];
    mapping: { before: string; after: string }[] | null;
  };
  /** Send back with apply(); required for operations that can remove data. */
  preview_token?: string | null;
  details: {
    invalid_counts?: Record<string, number>;
    invalid_samples?: { row: number; column: string; value: CellValue }[];
    filled?: { column: string; filled: number; value: CellValue }[];
    [key: string]: unknown;
  };
}

export interface ApplyResult extends OperationPreview {
  applied: boolean;
  session: SessionInfo;
}

export interface CompareResult {
  original: Stats;
  current: Stats;
  rows_removed: number;
  columns_removed: number;
  cells_modified: number;
  operations: HistoryItem[];
  preview: {
    original: { columns: string[]; row_numbers: number[]; rows: CellValue[][] };
    current: { columns: string[]; row_numbers: number[]; rows: CellValue[][] };
  };
}

export interface OutlierReport {
  column: string;
  q1: number;
  q3: number;
  iqr: number;
  lower_bound: number;
  upper_bound: number;
  count: number;
  checked: number;
  outliers: { row: number; value: CellValue; position: "above" | "below" }[];
  note: string;
}

export interface AppConfig {
  max_upload_mb: number;
  session_ttl_minutes: number;
  max_page_size: number;
  formats: ImportFormat[];
  export_formats: ExportFormat[];
}

export interface CompareRow {
  /** 1-based row number in the uploaded file */
  row: number;
  original: CellValue[];
  /** null when the row was removed */
  current: CellValue[] | null;
  /** per current column: true when the value differs from the original */
  changed: boolean[] | null;
}

export interface CompareRowsPage {
  original_columns: string[];
  current_columns: string[];
  renamed_or_new: string[];
  rows: CompareRow[];
  page: number;
  page_size: number;
  total_rows: number;
  total_pages: number;
  changes_only: boolean;
}

// --------------------------------------------------------------------------- AI assistant

export interface AiStatus {
  enabled: boolean;
  ready: boolean;
  provider: "off" | "ollama" | "anthropic";
  model: string;
  label: string;
  /** true when the data stays on this computer */
  local: boolean;
  /** cloud AI: requests must include consent: true */
  needs_consent: boolean;
  sends_values: boolean;
  /** what is shared with the AI, in plain words */
  shared: string;
  problem: string | null;
}

export interface AiPlan {
  reply: string;
  steps: { operation: Operation; label: string; reason: string }[];
  rejected: { label: string; reason: string }[];
  shared: string;
  provider: string;
}

export interface AiMappings {
  column: string;
  mappings: { value: string; to: string }[];
  checked: number;
  truncated: boolean;
  shared: string;
  provider: string;
}

export interface AiSummary {
  summary: string;
  shared: string;
  provider: string;
}

export interface AiAnswer {
  question: string;
  /** false when the table cannot answer the question */
  possible: boolean;
  /** one-line answer built by the app from the calculated result */
  answer: string;
  description: string;
  /** how the result was calculated, in plain words */
  steps: string[];
  columns: string[];
  rows: CellValue[][];
  total_groups: number;
  rows_matched: number;
  notes: string[];
  shared: string;
  provider: string;
}
