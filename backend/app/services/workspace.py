"""Use-case layer: everything an API route needs, independent of FastAPI.

Keeping the HTTP layer thin means this logic is easy to unit test.
"""

from __future__ import annotations

import hmac
import math
import os
import re
import tempfile
import time

import pandas as pd
from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import AppError
from app.services import profiling
from app.services.exporters import write_export
from app.services.importers import FORMAT_LABELS, load_file, validate_filename
from app.services.memory import new_bytes
from app.services.operations import (
    DATA_LOSS_TYPES,
    LABELS,
    _canon,
    count_changed_cells,
    is_destructive,
    outlier_report,
    run_operation,
)
from app.services.sessions import HistoryEntry, Session, SessionStore, new_entry_id

PREVIEW_ROW_SAMPLE = 20
MAX_COLUMNS = 5000  # wider files are almost always a wrong separator, and every view is per-column


# --------------------------------------------------------------------------- session lifecycle

def temp_upload_path(filename: str) -> str:
    """A private temporary file for an upload; callers must delete it."""
    suffix = os.path.splitext(filename)[1][:10]
    fd, path = tempfile.mkstemp(prefix="cleandata_upload_", suffix=suffix)
    os.close(fd)
    return path


def create_session_from_path(store: SessionStore, filename: str | None, path: str, size: int,
                             requested_format: str | None = None, sheet: str | None = None) -> dict:
    """Import a file that has already been written to a temporary path."""
    safe_name = validate_filename(filename)
    if size > settings.max_upload_bytes:
        raise AppError("file_too_large", f"The file is larger than the {settings.max_upload_mb} MB limit.",
                       "Split the file into smaller parts or remove unneeded columns.", status=413)
    try:
        result = load_file(path, safe_name, requested_format, sheet)
    except MemoryError as exc:
        raise AppError("out_of_memory", "There is not enough memory to load this file.",
                       "Close other programs, or split the file into smaller parts.", status=507) from exc
    if result.df.shape[1] > MAX_COLUMNS:
        raise AppError("too_many_columns",
                       f"The file has {result.df.shape[1]:,} columns; the limit is {MAX_COLUMNS:,}.",
                       "Check that the right separator was used, or remove unneeded columns.", status=422)
    session, token = store.create(
        filename=safe_name,
        file_size=size,
        encoding=result.encoding,
        delimiter=result.delimiter,
        import_warnings=result.warnings,
        original=result.df,
        format=result.format,
        sheet=result.sheet,
        sheets=result.sheets,
    )
    return {"session_id": token, **session_info(session)}


def create_session(store: SessionStore, filename: str | None, raw: bytes,
                   requested_format: str | None = None, sheet: str | None = None) -> dict:
    """Import in-memory bytes (convenience for tests and small uploads)."""
    safe_name = validate_filename(filename)
    path = temp_upload_path(safe_name)
    try:
        with open(path, "wb") as f:
            f.write(raw)
        return create_session_from_path(store, safe_name, path, len(raw), requested_format, sheet)
    finally:
        _remove(path)


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def session_info(session: Session) -> dict:
    current = session.current
    return {
        "file": {
            "name": session.filename,
            "size": session.file_size,
            "encoding": session.encoding,
            "delimiter": session.delimiter,
            "format": session.format,
            "format_label": FORMAT_LABELS.get(session.format, session.format.upper()),
            "sheet": session.sheet,
            "sheets": session.sheets,
            "warnings": session.import_warnings,
        },
        "original_shape": {"rows": len(session.original), "columns": session.original.shape[1]},
        "current_shape": {"rows": len(current), "columns": current.shape[1]},
        "history": [h.public() for h in session.history],
        "log": [e.public() for e in session.log],
        "can_undo": session.can_undo,
        "expires_in_seconds": settings.session_ttl_minutes * 60,
    }


def _dataset(session: Session, which: str) -> pd.DataFrame:
    if which == "original":
        return session.original
    if which == "current":
        return session.current
    raise AppError("invalid_dataset", "Dataset must be 'original' or 'current'.", None)


# --------------------------------------------------------------------------- inspection

def _key(session: Session, which: str) -> str:
    return "original" if which == "original" else session.version_key


def column_types(session: Session, which: str = "current") -> dict[str, str]:
    df = _dataset(session, which)
    return session.cached((_key(session, which), "types"), lambda: profiling.column_types(df))


def stats(session: Session, which: str = "current") -> dict:
    df = _dataset(session, which)
    return session.cached((_key(session, which), "stats"), lambda: profiling.basic_stats(df))


def get_profile(session: Session, which: str = "current", light: bool = False) -> dict:
    """Full quality report, or a light version (types, missing counts, stats) for forms.

    The light version skips issue detection and unique counts, which are the
    expensive parts on large datasets.
    """
    df = _dataset(session, which)
    if light:
        types = column_types(session, which)
        rows = len(df)
        missing = df.isna().sum()
        columns = [{
            "name": str(c), "type": types[str(c)], "missing": int(missing[c]),
            "missing_pct": round(int(missing[c]) / rows * 100, 2) if rows else None,
            "completeness": round((rows - int(missing[c])) / rows * 100, 2) if rows else None,
            "unique": None,
            "is_text": bool(pd.api.types.is_string_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])),
        } for c in df.columns]
        return {"dataset": which, "stats": stats(session, which), "columns": columns,
                "type_distribution": profiling.type_distribution(columns), "issues": [], "light": True}

    def compute():
        return profiling.full_profile(df, column_types(session, which), stats(session, which))

    profile = dict(session.cached((_key(session, which), "profile"), compute))
    profile["dataset"] = which
    return profile


def _view_index(session: Session, which: str, df: pd.DataFrame, search: str | None,
                sort_by: str | None, sort_dir: str) -> pd.Index:
    """Row order for a filtered/sorted view, cached so paging stays fast on large data."""

    def compute():
        view = df
        if search:
            mask = pd.Series(False, index=df.index)
            for col in df.columns:
                mask |= _canon(df[col]).str.contains(search, case=False, regex=False).fillna(False).astype(bool)
            view = df.loc[mask]
        if sort_by:
            kind = column_types(session, which).get(sort_by, "text")
            numeric_text = profiling.is_numeric_type(kind) and pd.api.types.is_string_dtype(df[sort_by])
            key = profiling.numeric_view if numeric_text else None
            view = view.sort_values(by=sort_by, ascending=(sort_dir != "desc"), na_position="last",
                                    kind="stable", key=key)
        return view.index

    return session.cached((_key(session, which), "view", search, sort_by, sort_dir), compute)


def get_rows(session: Session, which: str = "current", page: int = 1, page_size: int = 100,
             search: str | None = None, sort_by: str | None = None, sort_dir: str = "asc") -> dict:
    df = _dataset(session, which)
    page_size = max(1, min(page_size, settings.max_page_size))
    term = (search or "").strip()[:200] or None
    if sort_by and sort_by not in df.columns:
        raise AppError("unknown_columns", f'Column "{sort_by}" not found.', None)
    if term or sort_by:
        index = _view_index(session, which, df, term, sort_by, sort_dir)
    else:
        index = df.index

    total = len(index)
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, total_pages))
    chunk = df.loc[index[(page - 1) * page_size: page * page_size]]
    types = column_types(session, which)
    return {
        "dataset": which,
        "columns": [{"name": str(c), "type": types.get(str(c), "text")} for c in df.columns],
        "rows": profiling.frame_rows(chunk),
        "row_numbers": [int(i) + 1 for i in chunk.index],
        "page": page,
        "page_size": page_size,
        "total_rows": total,
        "unfiltered_rows": len(df),
        "total_pages": total_pages,
    }


def get_outliers(session: Session, column: str) -> dict:
    return outlier_report(session.current, column)


def get_values(session: Session, column: str, limit: int = 500) -> dict:
    """The different values of one column with how often each appears (for value mapping)."""
    with session.lock:
        df = session.current
        if column not in df.columns:
            raise AppError("unknown_columns", f'Column "{column}" not found.', "Refresh the page and try again.", status=404)
        counts = _canon(df[column]).dropna().value_counts()
        return {
            "column": column,
            "distinct": int(len(counts)),
            "values": [{"value": str(v), "count": int(n)} for v, n in counts.head(limit).items()],
            "truncated": len(counts) > limit,
        }


# --------------------------------------------------------------------------- operations

def _describe(before: pd.DataFrame, op: BaseModel, result) -> dict:
    after = result.df
    changes: dict = {"cell_samples": [], "removed_rows": None, "removed_columns": [], "mapping": None}

    rename = None
    if op.type == "clean_column_names":
        mapping = result.details.get("mapping", [])
        changes["mapping"] = mapping
        rename = {m["before"]: m["after"] for m in mapping}

    if result.cells_changed:
        _, samples = count_changed_cells(before, after, rename, columns=result.details.get("touched"))
        changes["cell_samples"] = samples

    removed_index = result.details.get("removed_index") or []
    if removed_index:
        sample_idx = removed_index[:PREVIEW_ROW_SAMPLE]
        sample = before.loc[sample_idx]
        changes["removed_rows"] = {
            "columns": [str(c) for c in before.columns],
            "row_numbers": [int(i) + 1 for i in sample_idx],
            "rows": profiling.frame_rows(sample),
        }
    changes["removed_columns"] = result.details.get("removed_columns", [])

    details = {k: v for k, v in result.details.items() if k not in ("removed_index", "mapping", "touched")}
    return {
        "operation": {"type": op.type, "label": LABELS[op.type], "params": op.model_dump()},
        "summary": result.summary,
        "warnings": result.warnings,
        "blocked": result.blocked,
        "destructive": is_destructive(op),
        "changed": result.changed and not result.blocked,
        "rows_before": len(before),
        "rows_after": len(after),
        "columns_before": before.shape[1],
        "columns_after": after.shape[1],
        "rows_removed": result.rows_removed,
        "columns_removed": result.columns_removed,
        "cells_changed": result.cells_changed,
        "changes": changes,
        "details": details,
    }


def preview_operation(session: Session, op: BaseModel) -> dict:
    """Run an operation on the working data without storing the result.

    The response includes a `preview_token` bound to this exact operation and
    dataset version. Applying an operation that can remove data requires it,
    so data loss is always previewed first.
    """
    with session.lock:
        before = session.current
        result = run_operation(before, op)
        description = _describe(before, op, result)
        description["preview_token"] = session.preview_token(op.model_dump())
        return description


def apply_operation(session: Session, op: BaseModel, preview_token: str | None = None) -> dict:
    with session.lock:
        params = op.model_dump()
        if preview_token is not None and not session.check_preview_token(params, preview_token):
            raise AppError("preview_outdated",
                           "The data or the options changed since this preview was made.",
                           "Preview the operation again, then apply.", status=409)
        if is_destructive(op) and preview_token is None:
            raise AppError("preview_required",
                           "This operation can remove data, so it must be previewed before it is applied.",
                           "Call the preview endpoint first and send its preview_token with the apply request.",
                           status=428)
        description, entry = _apply_step(session, op)
        if entry is None:
            # Honest reporting: an operation that changed nothing is not recorded as applied.
            return {**description, "applied": False, "session": session_info(session)}
        return {**description, "applied": True, "step_id": entry.id, "session": session_info(session)}


def _apply_step(session: Session, op: BaseModel) -> tuple[dict, HistoryEntry | None]:
    """Run one operation on the working data and record it. Caller holds the session lock
    and has already checked the preview token. Returns (description, entry or None if unchanged)."""
    params = op.model_dump()
    before = session.current
    result = run_operation(before, op)
    if result.blocked:
        raise AppError("operation_blocked", result.blocked,
                       "Nothing was changed. Adjust the options and preview again.", status=422)
    description = _describe(before, op, result)
    if not result.changed:
        return description, None
    entry = HistoryEntry(
        id=new_entry_id(),
        type=op.type,
        label=LABELS[op.type],
        params=params,
        summary=result.summary,
        applied_at=time.time(),
        rows_before=len(before),
        rows_after=len(result.df),
        columns_before=before.shape[1],
        columns_after=result.df.shape[1],
        rows_removed=result.rows_removed,
        columns_removed=result.columns_removed,
        cells_changed=result.cells_changed,
        warnings=result.warnings,
        df=result.df,
        bytes=new_bytes(result.df, before),
    )
    session.push(entry, settings.max_history_snapshots, settings.max_history_bytes)
    return description, entry


# --------------------------------------------------------------------------- quick clean and report

def quick_clean_plan(session: Session) -> dict:
    from app.services.quick_clean import plan

    with session.lock:
        return session.cached((session.version_key, "quick_clean_plan"), lambda: plan(session.current))


def _quick_token(session: Session, ops: list[BaseModel]) -> str:
    return session.preview_token({"quick_clean": [op.model_dump() for op in ops]})


def preview_quick_clean(session: Session, ops: list[BaseModel]) -> dict:
    """Run the chosen steps one after another on a copy and report each one; nothing is stored."""
    with session.lock:
        work = before = session.current
        steps = []
        cells = 0
        for op in ops:
            result = run_operation(work, op)
            steps.append({"label": LABELS[op.type], "summary": result.summary, "changed": result.changed and not result.blocked,
                          "blocked": result.blocked, "warnings": result.warnings})
            if result.blocked:
                break
            cells += result.cells_changed
            work = result.df
        return {
            "steps": steps,
            "rows_before": len(before), "rows_after": len(work),
            "columns_before": before.shape[1], "columns_after": work.shape[1],
            "cells_changed": cells,
            "blocked": next((s["blocked"] for s in steps if s["blocked"]), None),
            "preview_token": _quick_token(session, ops),
        }


def apply_quick_clean(session: Session, ops: list[BaseModel], preview_token: str | None) -> dict:
    """Apply previewed steps; each becomes its own history entry so it can be undone separately."""
    with session.lock:
        if not preview_token or not hmac.compare_digest(_quick_token(session, ops), preview_token):
            raise AppError("preview_outdated", "The data or the chosen fixes changed since the preview.",
                           "Preview Quick Clean again, then apply.", status=409)
        steps = []
        for op in ops:
            description, entry = _apply_step(session, op)
            steps.append({"label": LABELS[op.type], "summary": description["summary"], "applied": entry is not None})
        return {"steps": steps, "applied": sum(s["applied"] for s in steps), "session": session_info(session)}


def change_report(session: Session) -> dict:
    from app.services.quick_clean import change_report as build

    with session.lock:
        return build(session.filename, session.original, session.current, [h.public() for h in session.history])


def undo(session: Session) -> dict:
    with session.lock:
        entry = session.undo()
        return {"undone": entry.public(), "session": session_info(session)}


def reset(session: Session) -> dict:
    with session.lock:
        removed = session.reset()
        return {"steps_removed": removed, "session": session_info(session)}


def history(session: Session) -> dict:
    """Active steps (what the working data consists of) and the full audit log."""
    with session.lock:
        return {
            "steps": [h.public() for h in session.history],
            "log": [e.public() for e in session.log],
            "can_undo": session.can_undo,
        }


def operations_catalog() -> list[dict]:
    """Every supported operation with its parameters, derived from the Pydantic models."""
    from app.schemas.operations import OPERATION_MODELS

    catalog = []
    for op_type, model in OPERATION_MODELS.items():
        schema = model.model_json_schema()
        props = {k: v for k, v in schema.get("properties", {}).items() if k != "type"}
        catalog.append({
            "type": op_type,
            "label": LABELS[op_type],
            "description": (model.__doc__ or "").strip(),
            "may_remove_data": op_type in DATA_LOSS_TYPES,
            "parameters": props,
            "required": [r for r in schema.get("required", []) if r != "type"],
        })
    return catalog


# --------------------------------------------------------------------------- comparison

def compare(session: Session, sample_rows: int = 20) -> dict:
    original, current = session.original, session.current
    o, c = stats(session, "original"), stats(session, "current")
    cells_modified = sum(h.cells_changed for h in session.history)
    return {
        "original": o,
        "current": c,
        "rows_removed": max(0, o["rows"] - c["rows"]),
        "columns_removed": max(0, o["columns"] - c["columns"]),
        "cells_modified": cells_modified,
        "operations": [h.public() for h in session.history],
        "preview": {
            "original": {
                "columns": [str(x) for x in original.columns],
                "row_numbers": [int(i) + 1 for i in original.index[:sample_rows]],
                "rows": profiling.frame_rows(original.head(sample_rows)),
            },
            "current": {
                "columns": [str(x) for x in current.columns],
                "row_numbers": [int(i) + 1 for i in current.index[:sample_rows]],
                "rows": profiling.frame_rows(current.head(sample_rows)),
            },
        },
    }


def _changed_mask(session: Session) -> pd.Series:
    """Rows of the original upload that were removed or have at least one changed cell."""
    original, current = session.original, session.current

    def compute():
        removed = ~original.index.isin(current.index)
        mask = pd.Series(removed, index=original.index)
        common = original.index.intersection(current.index)
        # Original columns that no longer exist under their old name (renamed or removed).
        gone = [_canon(original.loc[common, c]) for c in original.columns if c not in current.columns]
        for col in current.columns:
            if col not in original.columns:
                values = _canon(current.loc[common, col])
                if any(bool(((old.isna() & values.isna()) | (old == values).fillna(False)).all()) for old in gone):
                    continue  # a renamed column whose values did not change
                # A column added by an operation (split, merge, review flags): rows with a value changed.
                mask.loc[common] |= current.loc[common, col].notna().to_numpy()
                continue
            b, a = _canon(original.loc[common, col]), _canon(current.loc[common, col])
            diff = ~((b.isna() & a.isna()) | (b == a).fillna(False).astype(bool))
            mask.loc[common] |= diff.to_numpy()
        return mask

    return session.cached((session.version_key, "changed_rows"), compute)


def compare_rows(session: Session, page: int = 1, page_size: int = 50, changes_only: bool = False) -> dict:
    """Original and current values side by side, aligned by original row number.

    Cells are compared by column name; a renamed column has no counterpart and
    is not highlighted. Removed rows are returned with `current: None`.
    """
    page_size = max(1, min(page_size, settings.max_page_size))
    with session.lock:
        original, current = session.original, session.current
        index = original.index
        if changes_only:
            mask = _changed_mask(session)
            index = mask.index[mask.to_numpy()]
        total = len(index)
        total_pages = max(1, math.ceil(total / page_size))
        page = max(1, min(page, total_pages))
        idx = index[(page - 1) * page_size: page * page_size]
        orig_rows = profiling.frame_rows(original.loc[idx])
        present = idx[idx.isin(current.index)]
        cur_rows = dict(zip(present.tolist(), profiling.frame_rows(current.loc[present])))
        orig_pos = {str(c): i for i, c in enumerate(original.columns)}
        cur_cols = [str(c) for c in current.columns]
        rows = []
        for i, row_id in enumerate(idx.tolist()):
            cur = cur_rows.get(row_id)
            changed = None
            if cur is not None:
                changed = [
                    (c in orig_pos) and (cur[j] != orig_rows[i][orig_pos[c]])
                    for j, c in enumerate(cur_cols)
                ]
            rows.append({"row": int(row_id) + 1, "original": orig_rows[i], "current": cur, "changed": changed})
        return {
            "original_columns": [str(c) for c in original.columns],
            "current_columns": cur_cols,
            "renamed_or_new": [c for c in cur_cols if c not in orig_pos],
            "rows": rows,
            "page": page,
            "page_size": page_size,
            "total_rows": total,
            "total_pages": total_pages,
            "changes_only": changes_only,
        }


# --------------------------------------------------------------------------- export

from app.utils.filenames import safe_output_name  # noqa: E402,F401  (re-exported for callers)


EXPORT_FORMATS = {"csv": ("text/csv; charset=utf-8", ".csv"),
                  "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx")}


def export_file(session: Session, filename: str | None = None, fmt: str = "csv", bom: bool = False,
                protect_formulas: bool = False) -> tuple[str, str, str]:
    """Write the current working data to a temporary file.

    Returns (path, download name, media type). The caller streams the file and
    deletes it afterwards, so large exports never sit in memory as one string.
    """
    if fmt not in EXPORT_FORMATS:
        raise AppError("invalid_format", f'Cannot export as "{fmt}".', "Choose CSV or Excel (.xlsx).")
    media_type, ext = EXPORT_FORMATS[fmt]
    name = safe_output_name(filename, session.filename, ext)
    with session.lock:
        df = session.current
    fd, path = tempfile.mkstemp(prefix="cleandata_export_", suffix=ext)
    os.close(fd)
    try:
        write_export(df, path, fmt, bom=bom, protect_formulas=protect_formulas)
    except BaseException:
        _remove(path)
        raise
    return path, name, media_type


def export_csv(session: Session, filename: str | None = None, bom: bool = False) -> tuple[bytes, str]:
    """Export to bytes (convenience for tests)."""
    path, name, _ = export_file(session, filename, "csv", bom)
    try:
        with open(path, "rb") as f:
            return f.read(), name
    finally:
        _remove(path)
