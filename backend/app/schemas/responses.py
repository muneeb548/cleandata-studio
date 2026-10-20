"""Response models. They document the API (OpenAPI at /docs) and are checked
against the real service output in tests/test_schemas.py."""

from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Cell = str | int | float | bool | None
ColumnType = Literal["integer", "decimal", "text", "datetime", "boolean", "empty"]


# Tests set CLEANDATA_STRICT_SCHEMAS=1 so any undocumented field fails loudly.
# At runtime unknown fields are ignored rather than turning a response into a 500.
_EXTRA = "forbid" if os.getenv("CLEANDATA_STRICT_SCHEMAS") == "1" else "ignore"


class _Model(BaseModel):
    model_config = ConfigDict(extra=_EXTRA)


class ErrorBody(_Model):
    code: str = Field(examples=["file_too_large"])
    message: str = Field(examples=["The file is larger than the 100 MB limit."])
    hint: str | None = Field(None, examples=["Split the file into smaller parts or remove unneeded columns."])


class ErrorResponse(_Model):
    error: ErrorBody


class Health(_Model):
    status: Literal["ok"]


class AppConfig(_Model):
    max_upload_mb: int
    session_ttl_minutes: int
    max_page_size: int
    formats: list[str]
    export_formats: list[str]


class Shape(_Model):
    rows: int
    columns: int


class FileInfo(_Model):
    name: str
    size: int
    encoding: str | None
    delimiter: str | None
    format: str
    format_label: str
    sheet: str | None
    sheets: list[str]
    warnings: list[str]


class HistoryStep(_Model):
    id: str
    type: str
    label: str
    params: dict[str, Any]
    summary: str
    applied_at: float
    rows_before: int
    rows_after: int
    columns_before: int
    columns_after: int
    rows_removed: int
    columns_removed: int
    cells_changed: int
    warnings: list[str]
    undoable: bool = Field(description="False once the snapshot was dropped to respect the memory budget.")


class LogEvent(_Model):
    event: Literal["applied", "undone", "reset"]
    at: float
    step_id: str | None
    type: str | None
    label: str | None
    summary: str | None


class SessionInfo(_Model):
    file: FileInfo
    original_shape: Shape
    current_shape: Shape
    history: list[HistoryStep]
    log: list[LogEvent]
    can_undo: bool
    expires_in_seconds: int


class UploadResponse(SessionInfo):
    session_id: str = Field(description="Send this value in the X-Session-Id header of every other request.")


class Stats(_Model):
    rows: int
    columns: int
    total_cells: int
    missing_cells: int
    duplicate_rows: int
    columns_with_missing: int
    completeness: float | None = Field(description="Percentage of non-missing cells; null when the dataset has no cells.")
    empty_rows: int
    empty_columns: int


class ColumnProfile(_Model):
    name: str
    type: ColumnType
    missing: int
    missing_pct: float | None
    completeness: float | None
    unique: int | None
    is_text: bool
    min: Cell = None
    max: Cell = None
    mean: Cell = None
    median: Cell = None


class Issue(_Model):
    id: str
    severity: Literal["high", "medium", "low", "info"]
    title: str
    description: str
    column: str | None
    count: int | None
    suggested_operation: str | None
    example: str | None = Field(None, description="A real value from the data that triggered the issue (used to pre-fill fixes).")


class Profile(_Model):
    dataset: Literal["original", "current"]
    stats: Stats
    columns: list[ColumnProfile]
    type_distribution: dict[str, int]
    issues: list[Issue]
    light: bool = False


class RowsColumn(_Model):
    name: str
    type: ColumnType


class RowsPage(_Model):
    dataset: Literal["original", "current"]
    columns: list[RowsColumn]
    rows: list[list[Cell]]
    row_numbers: list[int] = Field(description="1-based position of each row in the uploaded file.")
    page: int
    page_size: int
    total_rows: int
    unfiltered_rows: int
    total_pages: int


class OperationInfo(_Model):
    type: str
    label: str
    description: str
    may_remove_data: bool
    parameters: dict[str, Any] = Field(description="JSON Schema of each parameter.")
    required: list[str]


class OperationRef(_Model):
    type: str
    label: str
    params: dict[str, Any]


class CellChange(_Model):
    row: int
    column: str
    before: Cell
    after: Cell


class RemovedRows(_Model):
    columns: list[str]
    row_numbers: list[int]
    rows: list[list[Cell]]


class Mapping(_Model):
    before: str
    after: str


class Changes(_Model):
    cell_samples: list[CellChange]
    removed_rows: RemovedRows | None
    removed_columns: list[str]
    mapping: list[Mapping] | None


class OperationPreview(_Model):
    operation: OperationRef
    summary: str
    warnings: list[str]
    blocked: str | None = Field(description="Set when the operation must not be applied (e.g. invalid conversions with on_error=abort).")
    destructive: bool
    changed: bool
    rows_before: int
    rows_after: int
    columns_before: int
    columns_after: int
    rows_removed: int
    columns_removed: int
    cells_changed: int
    changes: Changes
    details: dict[str, Any]
    preview_token: str | None = None


class ApplyResponse(OperationPreview):
    applied: bool = Field(description="False when the operation would not change anything (nothing is recorded).")
    step_id: str | None = None
    session: SessionInfo


class UndoResponse(_Model):
    undone: HistoryStep
    session: SessionInfo


class ResetResponse(_Model):
    steps_removed: int
    session: SessionInfo


class HistoryResponse(_Model):
    steps: list[HistoryStep] = Field(description="Applied steps that make up the current working data, oldest first.")
    log: list[LogEvent] = Field(description="Every applied, undone and reset event, oldest first.")
    can_undo: bool


class QuickStep(_Model):
    id: str
    title: str
    label: str
    summary: str
    operation: dict[str, Any]
    selected: bool
    note: str | None
    warnings: list[str]


class QuickCleanPlan(_Model):
    steps: list[QuickStep]
    needs_decision: list[str] = Field(description="Things Quick Clean will not change because a person must decide.")


class QuickPreviewStep(_Model):
    label: str
    summary: str
    changed: bool
    blocked: str | None
    warnings: list[str]


class QuickCleanPreview(_Model):
    steps: list[QuickPreviewStep]
    rows_before: int
    rows_after: int
    columns_before: int
    columns_after: int
    cells_changed: int
    blocked: str | None
    preview_token: str


class QuickAppliedStep(_Model):
    label: str
    summary: str
    applied: bool


class QuickCleanResult(_Model):
    steps: list[QuickAppliedStep]
    applied: int
    session: SessionInfo


class ReportStep(_Model):
    label: str
    summary: str


class ReviewColumn(_Model):
    column: str
    rows: int


class ChangeReport(_Model):
    file: str
    rows_before: int
    rows_after: int
    columns_before: int
    columns_after: int
    steps: list[ReportStep]
    review: list[ReviewColumn]
    open_items: list[str]
    message: str = Field(description="A ready-to-send summary for the client.")


class Recipe(_Model):
    app: Literal["CleanData Studio"]
    kind: Literal["cleaning-recipe"]
    version: int
    name: str
    source_file: str
    created_at: str
    steps: list[dict[str, Any]] = Field(description="Operations in the order they were applied.")


class ValueCount(_Model):
    value: str
    count: int


class ColumnValues(_Model):
    column: str
    distinct: int = Field(description="Number of different non-empty values in the column.")
    values: list[ValueCount] = Field(description="Most frequent first.")
    truncated: bool = Field(description="True when there are more different values than were returned.")


class OutlierRow(_Model):
    row: int
    value: Cell
    position: Literal["above", "below"]


class OutlierReport(_Model):
    column: str
    q1: float
    q3: float
    iqr: float
    lower_bound: float
    upper_bound: float
    count: int
    checked: int
    outliers: list[OutlierRow]
    note: str


class PreviewTable(_Model):
    columns: list[str]
    row_numbers: list[int]
    rows: list[list[Cell]]


class ComparePreview(_Model):
    original: PreviewTable
    current: PreviewTable


class CompareResponse(_Model):
    original: Stats
    current: Stats
    rows_removed: int
    columns_removed: int
    cells_modified: int
    operations: list[HistoryStep]
    preview: ComparePreview


class CompareRow(_Model):
    row: int
    original: list[Cell]
    current: list[Cell] | None
    changed: list[bool] | None


class CompareRowsPage(_Model):
    original_columns: list[str]
    current_columns: list[str]
    renamed_or_new: list[str]
    rows: list[CompareRow]
    page: int
    page_size: int
    total_rows: int
    total_pages: int
    changes_only: bool


# --------------------------------------------------------------------------- AI assistant

class AiStatus(_Model):
    enabled: bool = Field(description="False when AI_PROVIDER=off.")
    ready: bool = Field(description="True when requests can be answered right now.")
    provider: Literal["off", "ollama", "anthropic"]
    model: str
    label: str
    local: bool = Field(description="True when the data stays on this computer.")
    needs_consent: bool = Field(description="True for a cloud AI: requests must include consent=true.")
    sends_values: bool = Field(description="True when example values from the file are shared with the AI.")
    shared: str = Field(description="What is shared with the AI, in plain words.")
    problem: str | None = Field(description="Why the AI is not ready, and how to fix it.")


class AiStep(_Model):
    operation: dict[str, Any] = Field(description="A validated operation, ready for /api/quick-clean/preview.")
    label: str
    reason: str


class AiRejectedStep(_Model):
    label: str
    reason: str


class AiPlan(_Model):
    reply: str
    steps: list[AiStep]
    rejected: list[AiRejectedStep] = Field(description="Steps the AI proposed that the app refused, with the reason.")
    shared: str
    provider: str


class AiMapping(_Model):
    value: str
    to: str


class AiMappings(_Model):
    column: str
    mappings: list[AiMapping] = Field(description="Ready for the map_values operation.")
    checked: int = Field(description="Number of different values the AI looked at.")
    truncated: bool
    shared: str
    provider: str


class AiSummary(_Model):
    summary: str
    shared: str
    provider: str
