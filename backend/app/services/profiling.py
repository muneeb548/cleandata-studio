"""Data quality statistics and issue detection. Every number is calculated from
the actual DataFrame; nothing here is hardcoded."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from app.services.csv_loader import STRING_DTYPE

LOGICAL_TYPES = ("integer", "decimal", "text", "datetime", "boolean", "empty")
PLACEHOLDER_TOKENS = {"na", "n/a", "null", "none", "nan", "-", "--", "?", "missing", "#n/a"}


# --------------------------------------------------------------------------- types

def numeric_view(series: pd.Series) -> pd.Series:
    """Numbers parsed from a column (NaN where the value is not a number)."""
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return pd.to_numeric(series, errors="coerce").astype("float64")
    text = series.astype(STRING_DTYPE).str.strip()
    # Accept thousands separators like "1,250,000" but never "1,5" (ambiguous decimal comma).
    if text.str.contains(",", regex=False).any():
        thousands = text.str.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?").fillna(False)
        text = text.where(~thousands, text.str.replace(",", "", regex=False))
    return pd.to_numeric(text, errors="coerce").astype("float64")


def logical_type(series: pd.Series) -> str:
    """Human-friendly type of a column, inferred from its values."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "decimal"
    non_missing = series.dropna()
    if len(non_missing) == 0:
        return "empty"
    # Fast path for large text columns: if the first values are not numbers,
    # the column is text and the expensive full parse can be skipped.
    if len(non_missing) > 2000 and numeric_view(non_missing.iloc[:2000]).isna().any():
        return "text"
    nums = numeric_view(non_missing)
    if nums.notna().all() and np.isfinite(nums).all():
        text = non_missing.astype(STRING_DTYPE).str.strip()
        # "007" style values are identifiers, not numbers: keep them as text.
        leading_zero = text.str.match(r"^-?0\d").fillna(False).any()
        if leading_zero:
            return "text"
        is_whole = (nums % 1 == 0).all() and not text.str.contains(r"[.eE]", regex=True).fillna(False).any()
        return "integer" if is_whole else "decimal"
    return "text"


def is_numeric_type(kind: str) -> bool:
    return kind in ("integer", "decimal")


# JSON conversion helpers live in app.utils.serialization (re-exported here).
from app.utils.serialization import frame_rows, to_jsonable  # noqa: E402,F401


# --------------------------------------------------------------------------- stats

def basic_stats(df: pd.DataFrame) -> dict:
    rows, cols = df.shape
    total_cells = rows * cols
    missing = int(df.isna().sum().sum()) if total_cells else 0
    duplicates = int(df.duplicated().sum()) if rows and cols else 0
    columns_with_missing = int((df.isna().sum() > 0).sum()) if cols else 0
    completeness = None if total_cells == 0 else round((total_cells - missing) / total_cells * 100, 2)
    return {
        "rows": rows,
        "columns": cols,
        "total_cells": total_cells,
        "missing_cells": missing,
        "duplicate_rows": duplicates,
        "columns_with_missing": columns_with_missing,
        "completeness": completeness,
        "empty_rows": int(df.isna().all(axis=1).sum()) if rows and cols else 0,
        "empty_columns": int(df.isna().all(axis=0).sum()) if cols and rows else 0,
    }


def column_types(df: pd.DataFrame) -> dict[str, str]:
    return {str(c): logical_type(df[c]) for c in df.columns}


def column_profiles(df: pd.DataFrame, types: dict[str, str] | None = None) -> list[dict]:
    rows = len(df)
    result = []
    for name in df.columns:
        s = df[name]
        missing = int(s.isna().sum())
        kind = types[str(name)] if types else logical_type(s)
        entry = {
            "name": str(name),
            "type": kind,
            "missing": missing,
            "missing_pct": round(missing / rows * 100, 2) if rows else None,  # no rows: a percentage is meaningless
            "completeness": round((rows - missing) / rows * 100, 2) if rows else None,
            "unique": int(s.nunique(dropna=True)),
            # True when values are stored as text (text-only operations are allowed).
            "is_text": bool(pd.api.types.is_string_dtype(s) and not pd.api.types.is_bool_dtype(s)),
        }
        if is_numeric_type(kind):
            nums = numeric_view(s).dropna()
            if len(nums):
                entry.update(
                    {
                        "min": to_jsonable(nums.min()),
                        "max": to_jsonable(nums.max()),
                        "mean": to_jsonable(round(float(nums.mean()), 4)),
                        "median": to_jsonable(float(nums.median())),
                    }
                )
        result.append(entry)
    return result


def type_distribution(profiles: list[dict]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for p in profiles:
        dist[p["type"]] = dist.get(p["type"], 0) + 1
    return dist


# --------------------------------------------------------------------------- issues

def iqr_outliers(series: pd.Series) -> dict | None:
    nums = numeric_view(series)
    nums = nums.where(np.isfinite(nums))  # ignore +/-Infinity when computing quartiles
    valid = nums.dropna()
    if len(valid) < 4:
        return None
    q1, q3 = float(valid.quantile(0.25)), float(valid.quantile(0.75))
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    mask = (nums < lower) | (nums > upper)
    return {"q1": q1, "q3": q3, "iqr": iqr, "lower": lower, "upper": upper, "mask": mask.fillna(False)}


def _looks_like_dates(series: pd.Series) -> bool:
    sample = series.dropna().astype(STRING_DTYPE).head(200)
    if len(sample) < 3:
        return False
    if not sample.str.contains(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}", regex=True).fillna(False).all():
        return False
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    return bool(parsed.notna().mean() >= 0.9)


def _n(count: int, word: str) -> str:
    return f"{count:,} {word}{'' if count == 1 else 's'}"


def detect_issues(df: pd.DataFrame, profiles: list[dict] | None = None, stats: dict | None = None) -> list[dict]:
    issues: list[dict] = []
    rows = len(df)
    if profiles is None:
        profiles = column_profiles(df)
    by_name = {p["name"]: p for p in profiles}

    def add(issue_id, severity, title, description, *, column=None, count=None, operation=None, example=None):
        issues.append(
            {
                "id": issue_id,
                "severity": severity,
                "title": title,
                "description": description,
                "column": column,
                "count": count,
                "suggested_operation": operation,
                "example": example,  # a real value from the data, used to pre-fill fixes
            }
        )

    if rows == 0:
        add("no_rows", "high", "Dataset has no rows", "The file has a header but no data rows.")
        return issues

    if stats is None:
        stats = basic_stats(df)
    dups = stats["duplicate_rows"]
    if dups:
        add("duplicates", "medium", _n(dups, "duplicate row"),
            "Rows that are exact copies of an earlier row.", count=dups, operation="remove_duplicates")

    empty_rows = stats["empty_rows"]
    if empty_rows:
        add("empty_rows", "medium", f"{_n(empty_rows, 'completely empty row')}",
            "Rows where every value is missing.", count=empty_rows, operation="remove_empty")

    for name in df.columns:
        s = df[name]
        p = by_name[str(name)]
        col = str(name)
        if p["missing"] == rows:
            add(f"empty_col:{col}", "medium", f'Column "{col}" is completely empty',
                "Every value in this column is missing.", column=col, count=rows, operation="remove_empty")
            continue
        if p["missing"]:
            sev = "high" if p["missing_pct"] >= 30 else "medium"
            add(f"missing:{col}", sev, f'{_n(p["missing"], "missing value")} in "{col}"',
                f'{p["missing_pct"]}% of this column is empty.', column=col, count=p["missing"],
                operation="missing_values")

        if pd.api.types.is_string_dtype(s) or s.dtype == object:
            text = s.dropna().astype(STRING_DTYPE)
            if len(text) == 0:
                continue
            stripped = text.str.strip()
            ws_only = int((stripped == "").sum())
            padded = int(((text != stripped) & (stripped != "")).sum())
            if padded:
                add(f"whitespace:{col}", "low", f'Extra spaces in "{col}"',
                    f"{_n(padded, 'value')} with leading or trailing spaces.", column=col, count=padded,
                    operation="trim_whitespace")
            if ws_only:
                add(f"blank:{col}", "low", f'Blank-looking values in "{col}"',
                    f"{_n(ws_only, 'value')} containing only spaces. Trimming turns them into missing values.",
                    column=col, count=ws_only, operation="trim_whitespace")
            is_placeholder = stripped.str.lower().isin(PLACEHOLDER_TOKENS)
            placeholders = int(is_placeholder.sum())
            if placeholders:
                common = text[is_placeholder].value_counts()
                tokens = ", ".join(f'"{t}"' for t in common.index[:3])
                add(f"placeholder:{col}", "medium", f'Missing-value placeholders in "{col}"',
                    f"{_n(placeholders, 'value')} that look like placeholders ({tokens}). "
                    "They are not counted as missing until you replace them.",
                    column=col, count=placeholders, operation="find_replace", example=str(common.index[0]))
            # Spreadsheet apps may run text starting with =, +, - or @ as a formula when a CSV is opened.
            starts = stripped.str.match(r"^[=+\-@]").fillna(False).astype(bool)
            if starts.any():
                formula_like = starts & numeric_view(stripped).isna()
                n_formula = int(formula_like.sum())
                if n_formula:
                    add(f"formula:{col}", "info", f'Formula-like text in "{col}"',
                        f"{_n(n_formula, 'value')} {'starts' if n_formula == 1 else 'start'} with =, +, - or @. Spreadsheet apps may run them as formulas "
                        "when the CSV is opened. Use 'Protect against formulas' when downloading.",
                        column=col, count=n_formula, example=str(text[formula_like].iloc[0])[:100])

            if p["type"] == "text":
                # Estimate on a sample first; parse the whole column only when it looks mostly numeric.
                sample = text.iloc[np.linspace(0, len(text) - 1, min(len(text), 20000)).astype(int)] if len(text) > 20000 else text
                share = float(numeric_view(sample).notna().mean())
                if share >= 0.8:
                    nums = numeric_view(text)
                    share = float(nums.notna().mean())
                if 0.8 <= share < 1:
                    bad = int(nums.isna().sum())
                    add(f"mixed:{col}", "medium", f'Mixed types in "{col}"',
                        f"Mostly numbers, but {_n(bad, 'value')} {'is' if bad == 1 else 'are'} not numeric.", column=col, count=bad,
                        operation="convert_type")
                elif _looks_like_dates(text):
                    add(f"dates:{col}", "low", f'"{col}" looks like dates stored as text',
                        "Convert it to a datetime column to sort and analyse it correctly.", column=col,
                        operation="convert_type")
                # Distinct spellings per lowercase value, computed vectorised (fast on large columns).
                pairs = pd.DataFrame({"low": stripped.str.lower(), "orig": stripped}).drop_duplicates()
                counts = pairs["low"].value_counts()
                mixed = counts[counts > 1]
                if len(mixed):
                    variants = pairs.loc[pairs["low"] == mixed.index[0], "orig"].head(2).tolist()
                    example = " vs ".join(f'"{v}"' for v in variants)
                    add(f"case:{col}", "low", f'Inconsistent capitalisation in "{col}"',
                        f"{_n(len(mixed), 'value')} written with different capitalisation (e.g. {example}).",
                        column=col, count=len(mixed), operation="standardize_text")

        if is_numeric_type(p["type"]):
            out = iqr_outliers(s)
            if out is not None:
                n = int(out["mask"].sum())
                if n:
                    add(f"outliers:{col}", "info", f'Possible outliers in "{col}"',
                        f"{_n(n, 'value')} outside the IQR range. An outlier is not necessarily an error.",
                        column=col, count=n, operation="outliers")

    bad_names = [c for c in df.columns if str(c) != str(c).strip() or " " in str(c).strip()]
    if bad_names:
        add("column_names", "low", f"{_n(len(bad_names), 'column name')} with spaces",
            "Spaces in column names make the data harder to use in code and tools.",
            count=len(bad_names), operation="clean_column_names")

    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    issues.sort(key=lambda i: order[i["severity"]])
    return issues


def full_profile(df: pd.DataFrame, types: dict[str, str] | None = None, stats: dict | None = None) -> dict:
    stats = stats or basic_stats(df)
    profiles = column_profiles(df, types)
    return {
        "stats": stats,
        "columns": profiles,
        "type_distribution": type_distribution(profiles),
        "issues": detect_issues(df, profiles, stats),
    }
