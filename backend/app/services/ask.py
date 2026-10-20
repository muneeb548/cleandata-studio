"""Answers questions about the data ("chat with your data") without letting the AI touch it.

The AI only fills in a small query plan: which rows to keep (filters), how to group them
and what to calculate. This module checks every part of the plan and computes the answer
with pandas. Every number the user sees therefore comes from the data, never from the AI.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.core.errors import AppError
from app.services.operations import _canon
from app.services.profiling import numeric_view
from app.utils.serialization import to_jsonable

FILTER_OPS = ["equals", "not_equals", "contains", "greater_than", "less_than", "is_missing", "is_not_missing"]
METRICS = ["count_rows", "count_distinct", "count_missing", "sum", "mean", "median", "min", "max"]
NUMERIC_METRICS = {"sum", "mean", "median", "min", "max"}
MAX_FILTERS = 5
MAX_GROUP_BY = 2
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MISSING_LABEL = "(missing)"

METRIC_TEXT = {
    "count_rows": "Rows", "count_distinct": "Different values", "count_missing": "Missing values",
    "sum": "Total", "mean": "Average", "median": "Median", "min": "Smallest", "max": "Largest",
}
OP_TEXT = {
    "equals": "is", "not_equals": "is not", "contains": "contains", "greater_than": "is greater than",
    "less_than": "is less than", "is_missing": "is empty", "is_not_missing": "is not empty",
}

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "possible": {"type": "boolean", "description": "false when the question cannot be answered from this table."},
        "reply": {"type": "string", "description": "When not possible: a short explanation for the user."},
        "description": {"type": "string", "description": "What is calculated, e.g. 'Customers per city'."},
        "filters": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "column": {"type": "string"},
                    "op": {"type": "string", "enum": FILTER_OPS},
                    "value": {"type": "string"},
                },
                "required": ["column", "op", "value"],
            },
        },
        "group_by": {"type": "array", "items": {"type": "string"}},
        "metric": {"type": "string", "enum": METRICS},
        "metric_column": {"type": "string", "description": "Column for the metric; empty for count_rows."},
        "sort": {"type": "string", "enum": ["desc", "asc", "none"]},
        "limit": {"type": "integer"},
    },
    "required": ["possible", "reply", "description", "filters", "group_by", "metric", "metric_column", "sort", "limit"],
}

SYSTEM = """You answer questions about a table by writing a query plan. You never see the full table
and you never calculate numbers yourself: the app runs your plan on the real data.

The plan:
- filters: rows to keep. op is one of: equals, not_equals, contains (text, ignores capitals),
  greater_than, less_than (numbers or dates), is_missing, is_not_missing (value ""). All filters must match.
- group_by: 0 to 2 columns. With group_by, the metric is calculated for each group.
- metric: count_rows (number of rows; metric_column ""), count_distinct, count_missing,
  sum, mean, median, min, max (these five need a numeric column).
- sort: desc for "most/highest/top", asc for "least/lowest", none otherwise. limit: how many groups to show (1-100, default 20).
- description: a short title for the result, in the user's language.
Use column names exactly as written in the data description. If the question cannot be answered with
such a plan (for example it asks for predictions, opinions, or data that is not in the table),
set possible to false and explain why in reply.
"""


def _bad(message: str) -> AppError:
    return AppError("ai_bad_plan", message, "Ask the question in a different way, naming the column if you can.", status=422)


def _number(value: str) -> float | None:
    try:
        number = float(str(value).replace(",", "").strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _compare(series: pd.Series, op: str, value: str, notes: list[str]) -> pd.Series:
    """Rows where `series <op> value` holds. Numbers are compared as numbers, then dates as dates."""
    target = _number(value)
    if target is not None:
        nums = numeric_view(series)
        if nums.notna().any():
            return (nums > target) if op == "greater_than" else (nums < target)
    when = pd.to_datetime(pd.Series([value]), errors="coerce").iloc[0]
    if pd.notna(when):
        dates = series if pd.api.types.is_datetime64_any_dtype(series) else pd.to_datetime(
            _canon(series), errors="coerce", format="mixed")
        if dates.notna().any():
            try:
                return (dates > when) if op == "greater_than" else (dates < when)
            except TypeError:  # time zones differ
                pass
    raise _bad(f'"{value}" cannot be compared with the values of "{series.name}".')


def _filter_mask(df: pd.DataFrame, flt: dict, notes: list[str]) -> pd.Series:
    col, op, value = flt["column"], flt["op"], str(flt.get("value", ""))
    s = df[col]
    if op == "is_missing":
        return s.isna()
    if op == "is_not_missing":
        return s.notna()
    if op in ("greater_than", "less_than"):
        return _compare(s, op, value, notes).fillna(False).astype(bool)
    text = _canon(s).str.strip().str.casefold()
    needle = value.strip().casefold()
    if op == "contains":
        return text.str.contains(needle, regex=False).fillna(False).astype(bool)
    hit = (text == needle).fillna(False).astype(bool)
    return ~hit if op == "not_equals" else hit


def check_plan(df: pd.DataFrame, plan: dict) -> dict:
    """The model's plan, cleaned up and checked against the real columns. Raises AppError if unusable."""
    columns = set(map(str, df.columns))

    def column(name: Any, what: str) -> str:
        name = str(name or "")
        if name not in columns:
            raise _bad(f'The {what} column "{name}" does not exist in this file.')
        return name

    metric = plan.get("metric") if plan.get("metric") in METRICS else None
    if metric is None:
        raise _bad("The AI chose a calculation the app does not support.")
    filters = []
    for f in (plan.get("filters") or [])[:MAX_FILTERS]:
        if not isinstance(f, dict) or f.get("op") not in FILTER_OPS:
            raise _bad("The AI wrote a filter the app does not understand.")
        filters.append({"column": column(f.get("column"), "filter"), "op": f["op"], "value": str(f.get("value", ""))[:200]})
    group_by = [column(g, "group") for g in (plan.get("group_by") or [])[:MAX_GROUP_BY]]
    if len(set(group_by)) != len(group_by):
        raise _bad("The same column was used twice for grouping.")
    metric_column = ""
    if metric != "count_rows":
        metric_column = column(plan.get("metric_column"), "calculation")
    try:
        limit = int(plan.get("limit") or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    return {
        "description": str(plan.get("description") or METRIC_TEXT[metric])[:200],
        "filters": filters,
        "group_by": group_by,
        "metric": metric,
        "metric_column": metric_column,
        "sort": plan.get("sort") if plan.get("sort") in ("desc", "asc", "none") else "none",
        "limit": max(1, min(limit, MAX_LIMIT)),
    }


def explain(plan: dict) -> list[str]:
    """The plan in plain words, so the user can check how the answer was calculated."""
    steps = []
    for f in plan["filters"]:
        value = "" if f["op"] in ("is_missing", "is_not_missing") else f' "{f["value"]}"'
        steps.append(f'Keep rows where {f["column"]} {OP_TEXT[f["op"]]}{value}')
    if plan["group_by"]:
        steps.append("Group by " + " and ".join(plan["group_by"]))
    what = METRIC_TEXT[plan["metric"]].lower()
    steps.append(f"Calculate: {what}" + (f' of {plan["metric_column"]}' if plan["metric_column"] else " (number of rows)"))
    if plan["group_by"] and plan["sort"] != "none":
        steps.append(("Highest" if plan["sort"] == "desc" else "Lowest") + f' first, top {plan["limit"]}')
    return steps


def _calc(values: pd.Series, metric: str):
    if metric == "count_rows":
        return len(values)
    if metric == "count_distinct":
        return int(values.nunique(dropna=True))
    if metric == "count_missing":
        return int(values.isna().sum())
    nums = values.dropna()
    if nums.empty:
        return None
    result = getattr(nums, metric)()
    return round(float(result), 4)


def run(df: pd.DataFrame, plan: dict) -> dict:
    """Execute a checked plan on the data."""
    notes: list[str] = []
    mask = pd.Series(True, index=df.index)
    for f in plan["filters"]:
        mask &= _filter_mask(df, f, notes)
    data = df[mask]
    metric, mcol = plan["metric"], plan["metric_column"]
    label = METRIC_TEXT[metric] + (f" of {mcol}" if mcol else "")

    if metric in NUMERIC_METRICS:
        values = numeric_view(data[mcol])
        not_numbers = int((values.isna() & data[mcol].notna()).sum())
        if values.notna().sum() == 0 and len(data):
            raise _bad(f'"{mcol}" has no numbers to calculate with.')
        if not_numbers:
            noun = "value is" if not_numbers == 1 else "values are"
            notes.append(f'{not_numbers:,} {noun} in "{mcol}" not plain numbers (for example "$1,250") and left out of the result. '
                         'Use "Clean numbers and currencies" first to include them.')
    elif mcol:
        values = data[mcol]
    else:
        values = pd.Series(1, index=data.index)

    if not plan["group_by"]:
        value = _calc(values, metric)
        return {"columns": [label], "rows": [[to_jsonable(value)]], "total_groups": 1, "rows_matched": int(len(data)),
                "notes": notes, "answer": f'{plan["description"]}: {_fmt(value)}'}

    keys = [_canon(data[g]).str.strip().fillna(MISSING_LABEL) for g in plan["group_by"]]
    grouped = values.groupby(keys, sort=False, dropna=False)
    if metric == "count_rows":
        result = grouped.size()
    elif metric == "count_distinct":
        result = grouped.nunique(dropna=True)
    elif metric == "count_missing":
        result = grouped.apply(lambda v: int(v.isna().sum()))
    else:
        result = grouped.agg(metric).round(4)
    if plan["sort"] != "none":
        result = result.sort_values(ascending=plan["sort"] == "asc", na_position="last", kind="stable")
    total = int(len(result))
    shown = result.head(plan["limit"])
    rows = []
    for key, value in shown.items():
        key = key if isinstance(key, tuple) else (key,)
        rows.append([str(k) for k in key] + [to_jsonable(None if pd.isna(value) else value)])
    if len(keys) == 1:
        labels = pd.Series(result.index.astype(str))
        folded = labels.str.casefold()
        if folded.duplicated().any():
            example = labels[folded == folded[folded.duplicated()].iloc[0]].head(2).tolist()
            notes.append(f'Some groups differ only in capital letters ("{example[0]}" and "{example[1]}"). '
                         "Quick Clean or Standardize text can merge them first.")
    if total > len(shown):
        notes.append(f"Showing {len(shown)} of {total:,} groups.")
    if rows:
        first = " / ".join(rows[0][:-1])
        answer = f'{plan["description"]}: {first} ({_fmt(rows[0][-1])})' if plan["sort"] != "none" else plan["description"]
    else:
        answer = f'{plan["description"]}: no rows match.'
    return {"columns": plan["group_by"] + [label], "rows": rows, "total_groups": total, "rows_matched": int(len(data)),
            "notes": notes, "answer": answer}


def _fmt(value) -> str:
    if value is None:
        return "no value"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value:,}" if isinstance(value, (int, float)) else str(value)
