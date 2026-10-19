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
    FlagRows,
    MergeColumns,
    MissingValues,
    Operation,
    RemoveDuplicates,
    RemoveEmpty,
    SplitColumn,
    StandardizeCountry,
    StandardizePhone,
    StandardizeText,
    TrimWhitespace,
)

DESTRUCTIVE_TYPES = {"remove_duplicates", "remove_empty"}
# Operation types that can remove rows or columns with at least one of their settings.
DATA_LOSS_TYPES = DESTRUCTIVE_TYPES | {"missing_values", "split_column", "merge_columns"}


def is_destructive(op: BaseModel) -> bool:
    """Operations that delete rows or columns need an explicit confirmation in the UI."""
    if op.type in DESTRUCTIVE_TYPES:
        return True
    if op.type == "split_column":
        return not op.keep_original
    if op.type == "merge_columns":
        return not op.keep_originals
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
        return bool(self.rows_removed or self.columns_removed or self.cells_changed or self.details.get("renamed")
                    or self.details.get("added_columns"))


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
        new_col = rename.get(col, col)
        if new_col not in after.columns:
            continue
        a = after[new_col] if common_index is before.index else after.loc[common_index, new_col]
        if col in before.columns:
            b = before[col] if common_index is before.index else before.loc[common_index, col]
        else:
            # A column the operation added: every value in it is new.
            b = pd.Series(pd.NA, index=a.index, dtype=STRING_DTYPE)
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


def _blank_to_na(s: pd.Series) -> pd.Series:
    s = s.astype(STRING_DTYPE).str.strip()
    return s.mask((s == "").fillna(False).astype(bool), pd.NA)


def _require_new_names(df: pd.DataFrame, names: list[str]) -> None:
    taken = [n for n in names if n in df.columns]
    if taken:
        raise AppError("column_exists", f"Column(s) already exist: {', '.join(taken)}.",
                       "Choose names that are not used yet. To replace the original column instead, "
                       "untick \"Keep the original\" and reuse its name.")


def _split_parts(text: pd.Series, separator: str, k: int, from_end: bool) -> list[pd.Series]:
    """Split each value into at most k parts. With from_end the extra text stays in the FIRST
    part ("Ali Raza Khan" -> "Ali Raza" + "Khan"); otherwise in the LAST part."""
    columns: list[list] = [[] for _ in range(k)]
    for value in text.tolist():
        if not isinstance(value, str):
            pieces: list = []
        elif separator == " ":
            pieces = value.rsplit(None, k - 1) if from_end else value.split(None, k - 1)
        else:
            pieces = value.rsplit(separator, k - 1) if from_end else value.split(separator, k - 1)
        if from_end and len(pieces) < k:
            pieces = [None] * (k - len(pieces)) + pieces  # fewer parts: fill from the right
        for i in range(k):
            columns[i].append(pieces[i] if i < len(pieces) else None)
    return [_blank_to_na(pd.Series(col, index=text.index, dtype=STRING_DTYPE)) for col in columns]


def split_column(df: pd.DataFrame, op: SplitColumn) -> OpResult:
    col = _require_columns(df, [op.column])[0]
    _require_text(df, [col], "Splitting")
    # When the original is removed, its name may be reused for one of the new columns.
    _require_new_names(df, [n for n in op.names if op.keep_original or n != col])
    k = len(op.names)
    text = df[col].str.strip()
    parts = _split_parts(text, op.separator, k, op.split_from == "end")
    out = df.copy(deep=False)
    position = list(df.columns).index(col)
    removed: list[str] = []
    if op.keep_original:
        position += 1
    else:
        out = out.drop(columns=[col])
        removed = [] if col in op.names else [col]  # a reused name is replaced, not removed
    for i, name in enumerate(op.names):
        out.insert(position + i, name, parts[i])
    filled_cells = int(sum(int(p.notna().sum()) for p in parts))
    sep_label = "spaces" if op.separator == " " else f'"{op.separator}"'
    summary = f'Split "{col}" on {sep_label} into {_plural(k, "column")}: {", ".join(op.names)}.'
    if not op.keep_original:
        summary += f' Replaced the original "{col}" column.' if col in op.names else f' Removed the original "{col}" column.'
    warnings = []
    single = sum(1 for p in zip(*[x.notna().tolist() for x in parts]) if sum(p) == 1)
    if single:
        target = op.names[-1] if op.split_from == "end" else op.names[0]
        warnings.append(f'{_plural(single, "value")} in "{col}" had nothing to split, so only "{target}" was filled.')
    return OpResult(out, summary, cells_changed=filled_cells, columns_removed=len(removed), warnings=warnings,
                    details={"added_columns": list(op.names), "removed_columns": removed, "touched": list(op.names)})


def merge_columns(df: pd.DataFrame, op: MergeColumns) -> OpResult:
    cols = _require_columns(df, op.columns)
    if len(cols) < 2:
        raise AppError("no_columns", "Select at least two different columns to merge.", None)
    # When the originals are removed, one of their names may be reused for the new column.
    if op.keep_originals or op.new_name not in cols:
        _require_new_names(df, [op.new_name])
    merged = _blank_to_na(_canon(df[cols[0]]))
    for c in cols[1:]:
        part = _blank_to_na(_canon(df[c]))
        both = merged.notna() & part.notna()
        joined = (merged + op.separator + part).where(both)
        merged = joined.fillna(merged).fillna(part).astype(STRING_DTYPE)
    out = df.copy(deep=False)
    last = max(list(df.columns).index(c) for c in cols)
    removed: list[str] = []
    if op.keep_originals:
        position = last + 1
    else:
        # The new column takes the place of the last merged column.
        position = sum(1 for i, c in enumerate(df.columns) if i < last and c not in cols)
        out = out.drop(columns=cols)
        removed = [c for c in cols if c != op.new_name]  # a reused name is replaced, not removed
    out.insert(position, op.new_name, merged)
    filled = int(merged.notna().sum())
    summary = f'Merged {", ".join(cols)} into "{op.new_name}".'
    if removed:
        summary += f" Removed the {_plural(len(removed), 'original column')}."
    return OpResult(out, summary, cells_changed=filled, columns_removed=len(removed),
                    details={"added_columns": [op.new_name], "removed_columns": removed, "touched": [op.new_name]})


# --------------------------------------------------------------------------- phone numbers

def _phonenumbers():
    try:
        import phonenumbers
    except ImportError as exc:  # pragma: no cover - depends on the installation
        raise AppError("missing_dependency", "Phone number support is not installed on the server.",
                       "Run: pip install -r requirements.txt", status=500) from exc
    return phonenumbers


def _check_region(region: str) -> str:
    pn = _phonenumbers()
    if region not in pn.SUPPORTED_REGIONS:
        raise AppError("unknown_region", f'"{region}" is not a supported country code.',
                       "Use a two-letter country code such as US, GB, DE, IN or PK.")
    return region


def _phone_text(s: pd.Series) -> pd.Series:
    """Text form of phone values; numbers that came from Excel as 4155552671.0 lose the .0."""
    text = _canon(s).str.strip()
    if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
        text = text.str.replace(r"\.0+$", "", regex=True)
    return text


def parse_phone(value: str, region: str | None):
    """A valid parsed phone number, or None. Without a region only +country numbers can be valid."""
    pn = _phonenumbers()
    try:
        number = pn.parse(value, region)
    except pn.NumberParseException:
        return None
    return number if pn.is_valid_number(number) else None


def _row_regions(df: pd.DataFrame, region_column: str | None, fallback: str | None) -> tuple[list[str | None], dict[str, int]]:
    """The phone region of every row: from the country column when it names a country
    that has phone numbers, otherwise the fallback. Also returns the unrecognised names."""
    from app.services.countries import country_code

    if not region_column:
        return [fallback] * len(df), {}
    _require_columns(df, [region_column])
    pn = _phonenumbers()
    regions: list[str | None] = []
    unknown: dict[str, int] = {}
    codes: dict[str, str | None] = {}
    for value in _canon(df[region_column]).tolist():
        if not isinstance(value, str) or not value.strip():
            regions.append(fallback)
            continue
        if value not in codes:
            code = country_code(value)
            codes[value] = code if code in pn.SUPPORTED_REGIONS else None
        if codes[value] is None:
            unknown[value.strip()] = unknown.get(value.strip(), 0) + 1
        regions.append(codes[value] or fallback)
    return regions, unknown


def _unknown_warning(unknown: dict[str, int], column: str, fallback: str | None) -> str:
    shown = ", ".join(f'"{v}"' for v in list(unknown)[:5]) + (", ..." if len(unknown) > 5 else "")
    use = f"so {fallback} was used for those rows" if fallback else "so only numbers with a + country code were accepted there"
    return f'{_plural(sum(unknown.values()), "row")} in "{column}" did not name a known country ({shown}), {use}.'


def standardize_phone(df: pd.DataFrame, op: StandardizePhone) -> OpResult:
    cols = _require_columns(df, op.columns)
    pn = _phonenumbers()
    region = _check_region(op.region)
    if op.region_column and op.region_column in cols:
        raise AppError("bad_country_column", f'"{op.region_column}" cannot be both a phone column and the country column.',
                       "Choose the column that holds the country names.")
    regions, unknown = _row_regions(df, op.region_column, region)
    fmt = {"national": pn.PhoneNumberFormat.NATIONAL, "international": pn.PhoneNumberFormat.INTERNATIONAL,
           "e164": pn.PhoneNumberFormat.E164}[op.format]
    out = df.copy(deep=False)
    invalid_counts: dict[str, int] = {}
    invalid_samples: list[dict] = []
    for c in cols:
        text = _phone_text(df[c])
        cache: dict[tuple[str, str | None], str | None] = {}
        formatted_values: list[str | None] = []
        for value, row_region in zip(text.tolist(), regions):
            if not isinstance(value, str):
                formatted_values.append(None)
                continue
            key = (value, row_region)
            if key not in cache:
                number = parse_phone(value, row_region)
                cache[key] = pn.format_number(number, fmt) if number is not None else None
            formatted_values.append(cache[key])
        formatted = pd.Series(formatted_values, index=text.index, dtype=STRING_DTYPE)
        bad = (text.notna() & formatted.isna()).fillna(False).astype(bool)
        if bad.any():
            invalid_counts[c] = int(bad.sum())
            for idx in bad[bad].index[: max(0, 20 - len(invalid_samples))]:
                invalid_samples.append({"row": int(idx) + 1, "column": c, "value": to_jsonable(df[c].loc[idx])})
        fallback = text if op.on_invalid == "keep" else pd.Series(pd.NA, index=text.index, dtype=STRING_DTYPE)
        out[c] = formatted.where(~bad, fallback).astype(STRING_DTYPE)
    changed, _ = count_changed_cells(df, out, columns=cols)
    total_bad = sum(invalid_counts.values())
    label = {"national": "national", "international": "international", "e164": "E.164"}[op.format]
    summary = (f"Formatted {_plural(changed, 'phone number')} in {label} format." if changed
               else "All valid phone numbers are already in this format.")
    warnings = []
    if unknown:
        warnings.append(_unknown_warning(unknown, op.region_column, region))
    if total_bad:
        action = "left unchanged" if op.on_invalid == "keep" else "set to missing"
        where = f'the country in "{op.region_column}"' if op.region_column else region
        warnings.append(f"{_plural(total_bad, 'value')} could not be read as a valid phone number for {where} and "
                        f"{'was' if total_bad == 1 else 'were'} {action}. Use 'Flag rows' to mark them for review.")
    return OpResult(out, summary, cells_changed=changed, warnings=warnings,
                    details={"invalid_counts": invalid_counts, "invalid_samples": invalid_samples, "touched": cols})


# --------------------------------------------------------------------------- countries

def standardize_country(df: pd.DataFrame, op: StandardizeCountry) -> OpResult:
    from app.services.countries import country_code, country_name

    cols = _require_columns(df, op.columns)
    _require_text(df, cols, "Standardizing country names")
    out = df.copy(deep=False)
    invalid_counts: dict[str, int] = {}
    invalid_samples: list[dict] = []
    for c in cols:
        s = df[c]
        mapping: dict[str, str | None] = {}
        for value in s.dropna().unique():
            code = country_code(value)
            mapping[value] = None if code is None else (code if op.output == "code" else country_name(code))
        converted = pd.Series([mapping.get(v) if isinstance(v, str) else None for v in s.tolist()],
                              index=s.index, dtype=STRING_DTYPE)
        bad = (s.notna() & converted.isna() & (s.str.strip() != "").fillna(False)).fillna(False).astype(bool)
        if bad.any():
            invalid_counts[c] = int(bad.sum())
            for idx in bad[bad].index[: max(0, 20 - len(invalid_samples))]:
                invalid_samples.append({"row": int(idx) + 1, "column": c, "value": to_jsonable(s.loc[idx])})
        out[c] = converted.fillna(s.astype(STRING_DTYPE)).astype(STRING_DTYPE)  # unrecognised values stay as they were
    changed, _ = count_changed_cells(df, out, columns=cols)
    form = "ISO codes" if op.output == "code" else "full country names"
    summary = f"Wrote {_plural(changed, 'value')} as {form}." if changed else f"All recognised countries are already written as {form}."
    warnings = []
    total_bad = sum(invalid_counts.values())
    if total_bad:
        warnings.append(f"{_plural(total_bad, 'value')} {'is' if total_bad == 1 else 'are'} not a recognised country and "
                        f"{'was' if total_bad == 1 else 'were'} left unchanged. Fix them with Find and replace, or flag them.")
    return OpResult(out, summary, cells_changed=changed, warnings=warnings,
                    details={"invalid_counts": invalid_counts, "invalid_samples": invalid_samples, "touched": cols})


# --------------------------------------------------------------------------- review flags

EMAIL_RE = r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}"
FLAG_LABELS = {
    "missing": "Missing {col}",
    "invalid_email": "Invalid email in {col}",
    "invalid_phone": "Invalid phone in {col}",
    "not_number": "Not a number in {col}",
    "not_date": "Not a date in {col}",
    "duplicate_value": "Repeated {col}",
}


def _flag_mask(df: pd.DataFrame, rule) -> pd.Series:
    s = df[rule.column]
    present = s.notna()
    if rule.check == "missing":
        return ~present
    if rule.check == "invalid_email":
        text = _canon(s).str.strip()
        return present & ~text.str.fullmatch(EMAIL_RE).fillna(False).astype(bool)
    if rule.check == "invalid_phone":
        region = _check_region(rule.region) if rule.region else None
        regions, _ = _row_regions(df, rule.region_column, region)
        text = _phone_text(s)
        cache: dict[tuple[str, str | None], bool] = {}
        ok: list[bool] = []
        for value, row_region in zip(text.tolist(), regions):
            if not isinstance(value, str):
                ok.append(False)
                continue
            if (value, row_region) not in cache:
                cache[(value, row_region)] = parse_phone(value, row_region) is not None
            ok.append(cache[(value, row_region)])
        return present & ~pd.Series(ok, index=s.index, dtype=bool)
    if rule.check == "not_number":
        if is_numeric_type(logical_type(s)):
            return pd.Series(False, index=s.index)
        return present & numeric_view(s).isna()
    if rule.check == "not_date":
        if pd.api.types.is_datetime64_any_dtype(s):
            return pd.Series(False, index=s.index)
        parsed = pd.to_datetime(_canon(s).str.strip(), errors="coerce", format="mixed")
        return present & parsed.isna()
    # duplicate_value: the same value (ignoring case and outer spaces) appears in more than one row
    key = _canon(s).str.strip().str.lower()
    return present & key.duplicated(keep=False).fillna(False).astype(bool)


def flag_rows(df: pd.DataFrame, op: FlagRows) -> OpResult:
    _require_columns(df, [r.column for r in op.rules])
    name = op.column_name
    if name in {r.column for r in op.rules}:
        raise AppError("column_exists", f'"{name}" is one of the columns being checked.',
                       "Choose another name for the review column.")
    flag = pd.Series(pd.NA, index=df.index, dtype=STRING_DTYPE)
    counts = []
    for rule in op.rules:
        mask = _flag_mask(df, rule).fillna(False).astype(bool)
        label = FLAG_LABELS[rule.check].format(col=rule.column)
        with_label = (flag + "; " + label).fillna(label)
        flag = flag.where(~mask, with_label)
        counts.append({"column": rule.column, "check": rule.check, "rows": int(mask.sum())})
    flagged = int(flag.notna().sum())
    if not flagged:
        return OpResult(df.copy(deep=False), "No rows match the selected checks, so no review column was added.",
                        details={"rule_counts": counts})
    out = df.copy(deep=False)
    warnings = []
    added: list[str] = []
    if name in df.columns:
        warnings.append(f'The existing "{name}" column will be replaced with the new review notes.')
    else:
        added = [name]
    out[name] = flag
    changed, _ = count_changed_cells(df, out, columns=[name])
    summary = f'Flagged {_plural(flagged, "row")} for review in "{name}". No values were changed or removed.'
    return OpResult(out, summary, cells_changed=changed, warnings=warnings,
                    details={"added_columns": added, "rule_counts": counts, "touched": [name]})


HANDLERS = {
    "remove_duplicates": remove_duplicates,
    "missing_values": missing_values,
    "trim_whitespace": trim_whitespace,
    "standardize_text": standardize_text,
    "clean_column_names": clean_column_names,
    "convert_type": convert_type,
    "remove_empty": remove_empty,
    "find_replace": find_replace,
    "split_column": split_column,
    "merge_columns": merge_columns,
    "standardize_phone": standardize_phone,
    "standardize_country": standardize_country,
    "flag_rows": flag_rows,
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
    "split_column": "Split column",
    "merge_columns": "Merge columns",
    "standardize_phone": "Standardize phone numbers",
    "standardize_country": "Standardize country names",
    "flag_rows": "Flag rows for review",
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
