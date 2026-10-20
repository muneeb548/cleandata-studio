"""Data quality statistics and issue detection. Every number is calculated from
the actual DataFrame; nothing here is hardcoded."""

from __future__ import annotations

import math
import re
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


NUMERIC_DATE_RE = r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}"
_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)
_SEP = r"[ \-/.,]*"
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
# "Jan 15 2026", "January 15, 2026", "15 Jan 2026", "15-Jan-2026"
MONTH_NAME_DATE_RE = (
    rf"(?:{_DAY}{_SEP}{_MONTH}{_SEP}\d{{2,4}}|{_MONTH}{_SEP}{_DAY}{_SEP}\d{{2,4}})"
    r"(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?"
)
# Numeric dates written day first or month first, e.g. 15/01/2026 or 01/15/2026.
_DMY_RE = re.compile(r"^\s*(\d{1,2})[-/.](\d{1,2})[-/.]\d{2,4}\b")
MAX_DATE_SHAPE_VALUES = 5000


def _date_like_mask(text: pd.Series) -> pd.Series:
    numeric = text.str.contains(NUMERIC_DATE_RE, regex=True).fillna(False).astype(bool)
    named = text.str.strip().str.fullmatch(MONTH_NAME_DATE_RE, flags=re.IGNORECASE).fillna(False).astype(bool)
    return numeric | named


def _looks_like_dates(series: pd.Series) -> bool:
    sample = series.dropna().astype(STRING_DTYPE).head(200)
    if len(sample) < 3:
        return False
    if not _date_like_mask(sample).all():
        return False
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    return bool(parsed.notna().mean() >= 0.9)


def _date_shape(value: str) -> str:
    """The layout of a date string: 2026-01-15 -> Y-N-N, 15/01/2026 -> N/N/Y, Jan 15 2026 -> M N Y."""
    def repl(m: re.Match) -> str:
        digits = m.group(1)
        if digits is not None:
            return "Y" if len(digits) == 4 else "N"
        return "M"
    # "3rd" and "15th" count as a plain day number.
    return re.sub(r"(\d+)(?:st|nd|rd|th)?|[A-Za-z]+", repl, value.strip(), flags=re.IGNORECASE)


def date_format_summary(text: pd.Series) -> dict:
    """Distinct date layouts in a text column, with one real example per layout and a
    hint about whether numeric dates are written day first."""
    uniques = text.dropna().astype(STRING_DTYPE).str.strip().drop_duplicates().head(MAX_DATE_SHAPE_VALUES)
    examples: dict[str, str] = {}
    day_first = month_first = False
    for value in uniques:
        shape = _date_shape(value)
        examples.setdefault(shape, value)
        m = _DMY_RE.match(value)
        if m:
            first, second = int(m.group(1)), int(m.group(2))
            day_first = day_first or first > 12
            month_first = month_first or second > 12
    hint = "day_first" if day_first and not month_first else "month_first" if month_first and not day_first else None
    return {"formats": len(examples), "examples": list(examples.values()), "hint": hint}


_EMAIL_NAME_RE = re.compile(r"e-?mail", re.IGNORECASE)
_PHONE_NAME_RE = re.compile(r"phone|mobile|cell|tel\b|telephone|whatsapp|contact.?no", re.IGNORECASE)
_COUNTRY_NAME_RE = re.compile(r"country|nation", re.IGNORECASE)
_EMAIL_SHAPE = r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}"
MAX_CHECKED_VALUES = 5000


def _sample_unique(stripped: pd.Series) -> list[str]:
    values = stripped[stripped != ""].drop_duplicates()
    return values.head(MAX_CHECKED_VALUES).tolist()


def _contact_and_amount_issues(col: str, text: pd.Series, stripped: pd.Series, add, *, mostly_numeric: bool) -> None:
    """Emails, phone numbers, country names and amounts written as text: each with a Fix."""
    from app.services.operations import parse_amount  # local import: operations imports this module

    present = stripped[stripped != ""]
    if not len(present):
        return

    # Emails: untidy (capitals, spaces, mailto:) or impossible (ali@gmail, ali@@gmail.com)
    without_mailto = present.str.replace(r"^mailto:", "", regex=True, case=False)
    looks_valid = without_mailto.str.fullmatch(_EMAIL_SHAPE).fillna(False).astype(bool)
    if _EMAIL_NAME_RE.search(col) or float(looks_valid.mean()) >= 0.8:
        original = text[stripped != ""]
        untidy = int(((original != without_mailto.str.lower()) & looks_valid).sum())
        invalid = present[~looks_valid]
        if untidy or len(invalid):
            parts = []
            if untidy:
                parts.append(f"{_n(untidy, 'address')} with capitals, spaces or \"mailto:\"")
            if len(invalid):
                parts.append(f'{_n(len(invalid), "value")} that cannot be a real address (e.g. "{invalid.iloc[0]}")')
            add(f"emails:{col}", "medium" if len(invalid) else "low", f'Email addresses need cleanup in "{col}"',
                " and ".join(parts) + ".", column=col, count=untidy + len(invalid), operation="clean_email",
                example=str(invalid.iloc[0]) if len(invalid) else None)
        return

    # Phone numbers: the same kind of number written in several layouts
    if _PHONE_NAME_RE.search(col):
        layouts: dict[str, str] = {}
        without_code = 0
        for value in _sample_unique(stripped):
            if sum(ch.isdigit() for ch in value) >= 7:
                layouts.setdefault(re.sub(r"\d", "9", value), value)
                without_code += not value.startswith(("+", "00"))
        # Numbers that all start with a country code are already international, even if countries differ.
        if len(layouts) > 1 and without_code:
            shown = ", ".join(f'"{v}"' for v in list(layouts.values())[:3])
            add(f"phones:{col}", "low", f'Phone numbers written in different ways in "{col}"',
                f"{_n(len(layouts), 'different layout')} (e.g. {shown}). Write them all in one international format.",
                column=col, count=len(layouts), operation="standardize_phone")
        return

    # Country names: "USA", "U.S.A." and "america" for the same country
    if _COUNTRY_NAME_RE.search(col):
        from app.services.countries import country_code, country_name

        counts = present.value_counts()
        to_fix = 0
        example = None
        for value, n in counts.items():
            code = country_code(value)
            if code and value != country_name(code):
                to_fix += int(n)
                example = example or value
        if to_fix:
            add(f"countries:{col}", "low", f'Country names written in different ways in "{col}"',
                f'{_n(to_fix, "value")} like "{example}" can be written as the full country name.',
                column=col, count=to_fix, operation="standardize_country", example=example)
        return

    # Amounts stored as text: "$1,250.00", "Rs 1,25,000", "1.234,56 €"
    if mostly_numeric:
        return  # already reported as mixed types
    values = _sample_unique(stripped)
    parsed = [v for v in values if parse_amount(v)[0] is not None]
    marked = [v for v in parsed if re.search(r"[^\d.\-+]", v)]  # a currency sign, code or separator
    if values and marked and len(parsed) / len(values) >= 0.8:
        add(f"amounts:{col}", "medium", f'Numbers stored as text in "{col}"',
            f'Values like "{marked[0]}" contain currency signs or separators, so they cannot be summed or sorted. '
            "Convert them to real numbers.", column=col, count=len(parsed), operation="clean_numbers", example=marked[0])


def _n(count: int, word: str) -> str:
    if count == 1:
        return f"{count:,} {word}"
    return f"{count:,} {word}{'es' if word.endswith(('s', 'x', 'ch', 'sh')) else 's'}"


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
                    "They count as missing in the completeness score; replace them with real empty cells.",
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
                    summary = date_format_summary(text)
                    if summary["hint"] == "day_first":
                        tip = ' Values like these put the day first, so tick "Day comes first".'
                    elif summary["hint"] == "month_first":
                        tip = ' Values like these put the month first, so leave "Day comes first" unticked.'
                    else:
                        tip = ""
                    if summary["formats"] > 1:
                        shown = ", ".join(f'"{v}"' for v in summary["examples"][:3])
                        add(f"dates:{col}", "medium", f'Mixed date formats in "{col}"',
                            f"{summary['formats']} different date formats (e.g. {shown}). "
                            f"Convert to a date column so every value uses one format and sorts correctly.{tip}",
                            column=col, count=summary["formats"], operation="convert_type",
                            example=summary["examples"][0])
                    else:
                        add(f"dates:{col}", "low", f'"{col}" looks like dates stored as text',
                            f"Convert it to a datetime column to sort and analyse it correctly.{tip}", column=col,
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
                _contact_and_amount_issues(col, text, stripped, add, mostly_numeric=share >= 0.8)

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


def health(stats: dict, profiles: list[dict], issues: list[dict]) -> dict:
    """How clean the data really is, beyond empty cells.

    "Completeness" counts only truly empty cells, so a file full of "N/A", "null" or
    space-only cells can look 100% complete. Here those cells count as missing, and every
    column records how many problems were found in it, so a messy file never looks clean.
    """
    looks_empty: dict[str, int] = {}
    per_column: dict[str, int] = {}
    problems = [i for i in issues if i["severity"] != "info"]  # "info" = a note to review, not a problem
    for issue in issues:
        col = issue.get("column")
        if col is None:
            continue
        if issue["severity"] != "info":
            per_column[col] = per_column.get(col, 0) + 1
        kind = issue["id"].split(":", 1)[0]
        if kind in ("placeholder", "blank"):
            looks_empty[col] = looks_empty.get(col, 0) + int(issue.get("count") or 0)
    rows = stats["rows"]
    for p in profiles:
        empty = looks_empty.get(p["name"], 0)
        p["looks_empty"] = empty
        p["issues"] = per_column.get(p["name"], 0)  # problems only, notes not counted
        if rows:
            p["completeness"] = round((rows - p["missing"] - empty) / rows * 100, 2)
    total = stats["total_cells"]
    empty_total = sum(looks_empty.values())
    return {
        "looks_empty_cells": empty_total,
        "real_completeness": None if total == 0 else round((total - stats["missing_cells"] - empty_total) / total * 100, 2),
        "issues": len(problems),
        "notes": len(issues) - len(problems),
        "columns_with_issues": len(per_column),
        "needs_cleaning": bool(problems),
    }


def full_profile(df: pd.DataFrame, types: dict[str, str] | None = None, stats: dict | None = None) -> dict:
    stats = stats or basic_stats(df)
    profiles = column_profiles(df, types)
    issues = detect_issues(df, profiles, stats)
    return {
        "stats": stats,
        "columns": profiles,
        "type_distribution": type_distribution(profiles),
        "issues": issues,
        "health": health(stats, profiles, issues),
    }
