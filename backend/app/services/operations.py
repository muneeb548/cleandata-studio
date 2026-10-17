"""Cleaning operations.

Every operation is a pure function: it receives a DataFrame and validated
parameters and returns a *new* DataFrame plus a summary. It never mutates its
input. The same function powers both "preview" and "apply", so what the user
previews is exactly what gets applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel

from app.core.errors import AppError
from app.services.csv_loader import STRING_DTYPE
from app.services.profiling import is_numeric_type, logical_type, numeric_view, to_jsonable

SAMPLE_LIMIT = 25
MAX_SAFE_INT = 2**53


# Parameter models live in app.schemas.operations; re-exported here for convenience.
from app.schemas.operations import (  # noqa: E402,F401
    CleanColumnNames,
    ConvertType,
    FindReplace,
    MissingValues,
    Operation,
    RemoveDuplicates,
    RemoveEmpty,
    StandardizeText,
    TrimWhitespace,
)

DESTRUCTIVE_TYPES = {"remove_duplicates", "remove_empty"}
# Operation types that can remove rows or columns with at least one of their settings.
DATA_LOSS_TYPES = DESTRUCTIVE_TYPES | {"missing_values"}


def is_destructive(op: BaseModel) -> bool:
    """Operations that delete rows or columns need an explicit confirmation in the UI."""
    if op.type in DESTRUCTIVE_TYPES:
        return True
    return op.type == "missing_values" and op.strategy in ("drop_rows", "drop_columns")


# --------------------------------------------------------------------------- result

@dataclass
class OpResult:
    df: pd.DataFrame
    summary: str
    rows_removed: int = 0
    columns_removed: int = 0
    cells_changed: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    blocked: str | None = None  # set when the operation must not be applied

    @property
    def changed(self) -> bool:
        return bool(self.rows_removed or self.columns_removed or self.cells_changed or self.details.get("renamed"))


# --------------------------------------------------------------------------- helpers

def _canon(series: pd.Series) -> pd.Series:
    """Comparable text form of a column, used to count changed cells."""
    if pd.api.types.is_datetime64_any_dtype(series):
        out = series.dt.strftime("%Y-%m-%d %H:%M:%S").str.replace(" 00:00:00", "", regex=False)
        return out.astype(STRING_DTYPE)
    return series.astype(STRING_DTYPE)


def count_changed_cells(before: pd.DataFrame, after: pd.DataFrame, rename: dict[str, str] | None = None,
                        columns: list[str] | None = None) -> tuple[int, list[dict]]:
    """Count cells whose value changed, comparing rows/columns present in both frames.

    `columns` limits the comparison to the columns an operation touched, which
    keeps previews fast on large datasets.
    """
    rename = rename or {}
    common_index = before.index if before.index.equals(after.index) else before.index.intersection(after.index)
    total = 0
    samples: list[dict] = []
    for col in (columns if columns is not None else before.columns):
        if col not in before.columns:
            continue
        new_col = rename.get(col, col)
        if new_col not in after.columns:
            continue
        b = before[col] if common_index is before.index else before.loc[common_index, col]
        a = after[new_col] if common_index is before.index else after.loc[common_index, new_col]
        bc, ac = _canon(b), _canon(a)
        both_na = bc.isna() & ac.isna()
        equal = (bc == ac).fillna(False).astype(bool)
        changed = ~(both_na | equal)
        n = int(changed.sum())
        total += n
        if n and len(samples) < SAMPLE_LIMIT:
            for idx in changed[changed].index[: SAMPLE_LIMIT - len(samples)]:
                samples.append(
                    {"row": int(idx) + 1, "column": str(new_col),
                     "before": to_jsonable(b.loc[idx]), "after": to_jsonable(a.loc[idx])}
                )
    return total, samples


def _require_columns(df: pd.DataFrame, columns: list[str], *, allow_empty: bool = False) -> list[str]:
    cols = list(dict.fromkeys(columns))  # dedupe, keep order
    if not cols and not allow_empty:
        raise AppError("no_columns", "Select at least one column.", "Choose the columns this operation should change.")
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise AppError("unknown_columns", f"Column(s) not found: {', '.join(missing)}.",
                       "The dataset may have changed. Refresh the column list and try again.")
    return cols


def _text_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if pd.api.types.is_string_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]


def _require_text(df: pd.DataFrame, cols: list[str], action: str) -> None:
    bad = [c for c in cols if c not in _text_columns(df)]
    if bad:
        raise AppError("not_text", f"{action} only works on text columns. Not text: {', '.join(bad)}.",
                       "Convert these columns to text first, or deselect them.")


def _fmt_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.10g}"


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


# --------------------------------------------------------------------------- operations

def remove_duplicates(df: pd.DataFrame, op: RemoveDuplicates) -> OpResult:
    if df.shape[1] == 0:
        return OpResult(df.copy(deep=False), "No columns, so there are no duplicates.")
    dup_mask = df.duplicated(keep=op.keep)
    out = df.loc[~dup_mask].copy(deep=False)
    n = int(dup_mask.sum())
    if not n:
        return OpResult(out, "No duplicate rows found.")
    return OpResult(out, f"Removed {_plural(n, 'duplicate row')} (kept the {op.keep} occurrence).",
                    rows_removed=n, details={"removed_index": dup_mask[dup_mask].index.tolist()})


def missing_values(df: pd.DataFrame, op: MissingValues) -> OpResult:
    cols = _require_columns(df, op.columns)

    if op.strategy == "drop_rows":
        mask = df[cols].isna().any(axis=1)
        n = int(mask.sum())
        out = df.loc[~mask].copy(deep=False)
        if not n:
            return OpResult(out, "No rows with missing values in the selected columns.")
        return OpResult(out, f"Removed {_plural(n, 'row')} with missing values in {_plural(len(cols), 'column')}.",
                        rows_removed=n, details={"removed_index": mask[mask].index.tolist()})

    if op.strategy == "drop_columns":
        to_drop = [c for c in cols if df[c].isna().any()]
        skipped = [c for c in cols if c not in to_drop]
        out = df.drop(columns=to_drop).copy(deep=False)
        warnings = [f"Kept {len(skipped)} selected column(s) that have no missing values: {', '.join(skipped)}."] if skipped else []
        if not to_drop:
            return OpResult(out, "None of the selected columns contain missing values.", warnings=warnings)
        return OpResult(out, f"Removed {_plural(len(to_drop), 'column')} containing missing values: {', '.join(to_drop)}.",
                        columns_removed=len(to_drop), details={"removed_columns": to_drop}, warnings=warnings)

    out = df.copy(deep=False)
    warnings: list[str] = []
    filled_total = 0
    fill_report: list[dict] = []

    if op.strategy in ("fill_mean", "fill_median"):
        stat_name = "mean" if op.strategy == "fill_mean" else "median"
        non_numeric = [c for c in cols if not is_numeric_type(logical_type(df[c]))]
        if non_numeric:
            raise AppError("not_numeric", f"The {stat_name} can only be calculated for numeric columns. "
                           f"Not numeric: {', '.join(non_numeric)}.",
                           "Deselect these columns, or use 'Fill with a value' for text columns.")
        for c in cols:
            nums = numeric_view(df[c])
            if nums.notna().sum() == 0:
                raise AppError("all_missing", f'Column "{c}" has no values to calculate a {stat_name} from.',
                               "Remove the column or fill it with a constant value.")
            stat = float(nums.mean() if stat_name == "mean" else nums.median())
            missing = df[c].isna()
            n = int(missing.sum())
            if not n:
                continue
            s = df[c]
            if pd.api.types.is_string_dtype(s):
                out[c] = s.where(~missing, _fmt_number(round(stat, 6)))
            elif pd.api.types.is_integer_dtype(s) and not float(stat).is_integer():
                out[c] = s.astype("Float64").where(~missing, stat)
                warnings.append(f'"{c}" changed from integer to decimal because its {stat_name} is not a whole number.')
            else:
                out[c] = s.where(~missing, stat)
            filled_total += n
            fill_report.append({"column": c, "filled": n, "value": round(stat, 6)})
        summary = f"Filled {_plural(filled_total, 'missing value')} with the column {stat_name}."
    else:  # fill_constant
        if op.value is None or op.value == "":
            raise AppError("missing_value", "Enter the value to fill missing cells with.",
                           "Type a value, for example 0 or Unknown.")
        for c in cols:
            s = df[c]
            missing = s.isna()
            n = int(missing.sum())
            if not n:
                continue
            if pd.api.types.is_datetime64_any_dtype(s):
                parsed = pd.to_datetime(pd.Series([op.value]), errors="coerce")
                if parsed.isna().iloc[0]:
                    raise AppError("invalid_fill", f'"{op.value}" is not a valid date for column "{c}".',
                                   "Use a date like 2024-01-31.")
                out[c] = s.where(~missing, parsed.iloc[0])
            elif pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
                num = pd.to_numeric(pd.Series([op.value]), errors="coerce").iloc[0]
                if pd.isna(num):
                    raise AppError("invalid_fill", f'"{op.value}" is not a number, but column "{c}" is numeric.',
                                   "Enter a number, or convert the column to text first.")
                if pd.api.types.is_integer_dtype(s) and not float(num).is_integer():
                    out[c] = s.astype("Float64").where(~missing, float(num))
                else:
                    out[c] = s.where(~missing, num)
            else:
                if is_numeric_type(logical_type(s)) and pd.isna(pd.to_numeric(pd.Series([op.value]), errors="coerce").iloc[0]):
                    warnings.append(f'"{c}" contains numbers; filling with "{op.value}" makes it a text column.')
                out[c] = s.where(~missing, op.value)
            filled_total += n
            fill_report.append({"column": c, "filled": n, "value": op.value})
        summary = f'Filled {_plural(filled_total, "missing value")} with "{op.value}".'

    if not filled_total:
        return OpResult(out, "The selected columns have no missing values.", warnings=warnings)
    return OpResult(out, summary, cells_changed=filled_total,
                    details={"filled": fill_report, "touched": [r["column"] for r in fill_report]}, warnings=warnings)


def trim_whitespace(df: pd.DataFrame, op: TrimWhitespace) -> OpResult:
    if op.columns:
        cols = _require_columns(df, op.columns)
        _require_text(df, cols, "Trimming")
    else:
        cols = _text_columns(df)
    out = df.copy(deep=False)
    blanks = 0
    touched = []
    for c in cols:
        stripped = df[c].str.strip()
        empty = (stripped == "").fillna(False)
        if not ((stripped != df[c]).fillna(False).any() or empty.any()):
            continue  # unchanged columns keep sharing memory with the previous version
        blanks += int(empty.sum())
        out[c] = stripped.mask(empty, pd.NA)
        touched.append(c)
    changed, _ = count_changed_cells(df, out, columns=touched)
    if not changed:
        return OpResult(out, "No leading or trailing spaces found.")
    summary = f"Trimmed spaces in {_plural(changed, 'cell')}."
    if blanks:
        summary += f" {_plural(blanks, 'cell')} contained only spaces and are now missing."
    return OpResult(out, summary, cells_changed=changed, details={"columns": cols, "touched": touched})


def standardize_text(df: pd.DataFrame, op: StandardizeText) -> OpResult:
    cols = _require_columns(df, op.columns)
    _require_text(df, cols, "Changing text case")
    out = df.copy(deep=False)
    for c in cols:
        s = df[c]
        out[c] = s.str.lower() if op.case == "lower" else s.str.upper() if op.case == "upper" else s.str.title()
    changed, _ = count_changed_cells(df, out, columns=cols)
    label = {"lower": "lowercase", "upper": "UPPERCASE", "title": "Title Case"}[op.case]
    if not changed:
        return OpResult(out, f"All selected values are already in {label}.")
    return OpResult(out, f"Converted {_plural(changed, 'value')} to {label}.", cells_changed=changed,
                    details={"touched": cols})


def proposed_column_names(columns: list[str], replace_spaces: bool, lowercase: bool) -> list[str]:
    names: list[str] = []
    for i, original in enumerate(columns):
        name = str(original).strip()
        if replace_spaces:
            name = re.sub(r"\s+", "_", name)
            name = re.sub(r"_+", "_", name)
        else:
            name = re.sub(r"\s+", " ", name)
        if lowercase:
            name = name.lower()
        names.append(name or f"column_{i + 1}")
    # Resolve collisions deterministically: second "a" becomes "a_2", etc.
    result: list[str] = []
    used: set[str] = set()
    for name in names:
        candidate, n = name, 1
        while candidate in used:
            n += 1
            candidate = f"{name}_{n}"
        used.add(candidate)
        result.append(candidate)
    return result


def clean_column_names(df: pd.DataFrame, op: CleanColumnNames) -> OpResult:
    old = [str(c) for c in df.columns]
    new = proposed_column_names(old, op.replace_spaces, op.lowercase)
    mapping = [{"before": o, "after": n} for o, n in zip(old, new)]
    renamed = [m for m in mapping if m["before"] != m["after"]]
    out = df.copy(deep=False)
    out.columns = new
    if not renamed:
        return OpResult(out, "Column names are already clean.", details={"mapping": mapping, "renamed": 0})
    return OpResult(out, f"Renamed {_plural(len(renamed), 'column')}.", details={"mapping": mapping, "renamed": len(renamed)})


def convert_type(df: pd.DataFrame, op: ConvertType) -> OpResult:
    cols = _require_columns(df, op.columns)
    out = df.copy(deep=False)
    invalid_samples: list[dict] = []
    invalid_counts: dict[str, int] = {}

    for c in cols:
        s = df[c]
        present = s.notna()
        if op.target == "string":
            out[c] = _canon(s)
            continue
        if op.target in ("integer", "float"):
            nums = numeric_view(s)
            bad = present & (nums.isna() | ~np.isfinite(nums.fillna(0)))
            if op.target == "integer":
                bad = bad | (present & nums.notna() & ((nums % 1 != 0) | (nums.abs() > MAX_SAFE_INT)))
            good = nums.where(~bad)
            out[c] = good.round().astype("Int64") if op.target == "integer" else good.astype("Float64")
        else:  # datetime
            text = _canon(s).str.strip()
            try:
                if op.date_format:
                    parsed = pd.to_datetime(text, errors="coerce", format=op.date_format)
                else:
                    parsed = pd.to_datetime(text, errors="coerce", format="mixed", dayfirst=op.dayfirst)
            except (ValueError, TypeError) as exc:
                raise AppError("datetime_error", f'Dates in "{c}" could not be parsed consistently.',
                               "Try specifying a date format such as %Y-%m-%d or %d/%m/%Y.") from exc
            if getattr(parsed.dt, "tz", None) is not None:
                parsed = parsed.dt.tz_convert("UTC").dt.tz_localize(None)
            bad = present & parsed.isna()
            out[c] = parsed.where(~bad)
        n_bad = int(bad.sum())
        if n_bad:
            invalid_counts[c] = n_bad
            for idx in bad[bad].index[: max(0, 20 - len(invalid_samples))]:
                invalid_samples.append({"row": int(idx) + 1, "column": c, "value": to_jsonable(s.loc[idx])})

    total_bad = sum(invalid_counts.values())
    changed, _ = count_changed_cells(df, out, columns=cols)
    target_label = {"integer": "integer", "float": "decimal", "string": "text", "datetime": "datetime"}[op.target]
    details = {"invalid_counts": invalid_counts, "invalid_samples": invalid_samples, "target": op.target}

    if total_bad and op.on_error == "abort":
        return OpResult(df.copy(deep=False), f"{_plural(total_bad, 'value')} cannot be converted to {target_label}.",
                        details=details,
                        blocked=f"{_plural(total_bad, 'value')} cannot be converted to {target_label}. "
                                "Fix them, or choose to set invalid values to missing.")
    summary = f"Converted {_plural(len(cols), 'column')} to {target_label}."
    warnings = []
    if total_bad:
        summary += f" {_plural(total_bad, 'invalid value')} were set to missing."
        warnings.append(f"{_plural(total_bad, 'value')} could not be converted and became missing.")
    dtype_changed = any(str(df[c].dtype) != str(out[c].dtype) for c in cols)
    return OpResult(out, summary, cells_changed=changed, details={**details, "renamed": int(dtype_changed), "touched": cols},
                    warnings=warnings)


def remove_empty(df: pd.DataFrame, op: RemoveEmpty) -> OpResult:
    out = df
    rows_removed = cols_removed = 0
    removed_columns: list[str] = []
    removed_index: list[int] = []
    if op.target in ("columns", "both") and len(df):
        empty_cols = [c for c in df.columns if df[c].isna().all()]
        removed_columns = [str(c) for c in empty_cols]
        out = out.drop(columns=empty_cols)
        cols_removed = len(empty_cols)
    if op.target in ("rows", "both") and out.shape[1]:
        mask = df.loc[out.index].isna().all(axis=1)
        removed_index = mask[mask].index.tolist()
        out = out.loc[~mask]
        rows_removed = int(mask.sum())
    out = out.copy(deep=False)
    if not rows_removed and not cols_removed:
        return OpResult(out, "No completely empty rows or columns found.")
    parts = []
    if rows_removed:
        parts.append(_plural(rows_removed, "empty row"))
    if cols_removed:
        parts.append(_plural(cols_removed, "empty column"))
    return OpResult(out, "Removed " + " and ".join(parts) + ".", rows_removed=rows_removed,
                    columns_removed=cols_removed,
                    details={"removed_columns": removed_columns, "removed_index": removed_index})


def find_replace(df: pd.DataFrame, op: FindReplace) -> OpResult:
    cols = _require_columns(df, op.columns)
    _require_text(df, cols, "Find and replace")
    if op.find == "":
        raise AppError("empty_find", "Enter the text to find.", None)
    out = df.copy(deep=False)
    flags = 0 if op.case_sensitive else re.IGNORECASE
    for c in cols:
        s = df[c]
        if op.match == "exact":
            hits = (s == op.find) if op.case_sensitive else (s.str.lower() == op.find.lower())
            hits = hits.fillna(False).astype(bool)
            replacement = pd.NA if op.replace == "" else op.replace
            out[c] = s.mask(hits, replacement)
        else:
            replaced = s.str.replace(re.escape(op.find), op.replace.replace("\\", "\\\\"), regex=True, flags=flags)
            out[c] = replaced.mask((replaced == "").fillna(False), pd.NA)
    changed, _ = count_changed_cells(df, out, columns=cols)
    if not changed:
        return OpResult(out, f'No cells matched "{op.find}".')
    target = "missing" if op.replace == "" else f'"{op.replace}"'
    return OpResult(out, f'Replaced "{op.find}" with {target} in {_plural(changed, "cell")}.', cells_changed=changed,
                    details={"touched": cols})


HANDLERS = {
    "remove_duplicates": remove_duplicates,
    "missing_values": missing_values,
    "trim_whitespace": trim_whitespace,
    "standardize_text": standardize_text,
    "clean_column_names": clean_column_names,
    "convert_type": convert_type,
    "remove_empty": remove_empty,
    "find_replace": find_replace,
}

LABELS = {
    "remove_duplicates": "Remove duplicate rows",
    "missing_values": "Handle missing values",
    "trim_whitespace": "Trim whitespace",
    "standardize_text": "Standardize text case",
    "clean_column_names": "Clean column names",
    "convert_type": "Convert data type",
    "remove_empty": "Remove empty rows/columns",
    "find_replace": "Find and replace",
}


def run_operation(df: pd.DataFrame, op: BaseModel) -> OpResult:
    handler = HANDLERS[op.type]
    return handler(df, op)


# --------------------------------------------------------------------------- outliers (review only)

def outlier_report(df: pd.DataFrame, column: str, limit: int = 100) -> dict:
    if column not in df.columns:
        raise AppError("unknown_columns", f'Column "{column}" not found.', None, status=404)
    kind = logical_type(df[column])
    if not is_numeric_type(kind):
        raise AppError("not_numeric", f'"{column}" is not a numeric column.', "Outlier detection needs numbers.")
    from app.services.profiling import iqr_outliers

    res = iqr_outliers(df[column])
    if res is None:
        raise AppError("too_few_values", f'"{column}" needs at least 4 numeric values for IQR outlier detection.', None)
    mask = res["mask"]
    nums = numeric_view(df[column])
    flagged = nums[mask]
    order = (flagged - (res["q1"] + res["q3"]) / 2).abs().sort_values(ascending=False).index
    rows = [{"row": int(i) + 1, "value": to_jsonable(df[column].loc[i]),
             "position": "above" if nums.loc[i] > res["upper"] else "below"} for i in order[:limit]]
    return {
        "column": column,
        "q1": res["q1"], "q3": res["q3"], "iqr": res["iqr"],
        "lower_bound": res["lower"], "upper_bound": res["upper"],
        "count": int(mask.sum()),
        "checked": int(nums.notna().sum()),
        "outliers": rows,
        "note": "Values outside Q1 - 1.5*IQR and Q3 + 1.5*IQR. An outlier is not necessarily an error; "
                "review it before changing anything. This check never modifies your data.",
    }
