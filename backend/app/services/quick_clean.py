"""Quick Clean and the change report.

Quick Clean proposes only fixes that keep the meaning of the data: removing exact
copies, spaces, placeholder text, inconsistent spelling of the same word, and
standard formats for emails, phones, countries and dates. Anything that needs a
human decision (missing values, outliers, ambiguous dates, phones without a known
country) is listed instead of changed. Every proposed step is an ordinary
operation, so it is previewed, recorded in the history and can be undone.
"""

from __future__ import annotations

import re

import pandas as pd
from pydantic import TypeAdapter

from app.schemas.operations import Operation
from app.services import profiling
from app.services.csv_loader import STRING_DTYPE
from app.services.operations import EMAIL_RE, LABELS, run_operation

_OPERATION = TypeAdapter(Operation)

ID_NAME_RE = re.compile(r"(^|[\s_\-])(id|email|e-mail|code|sku|order|invoice|number|no)([\s_\-]|$)|^id|id$", re.IGNORECASE)
EMAIL_NAME_RE = re.compile(r"e-?mail", re.IGNORECASE)
PHONE_NAME_RE = re.compile(r"phone|mobile|cell|tel\b|telephone|whatsapp|contact.?no", re.IGNORECASE)
COUNTRY_NAME_RE = re.compile(r"country|nation", re.IGNORECASE)


def _text_columns(df: pd.DataFrame) -> list[str]:
    return [str(c) for c in df.columns if pd.api.types.is_string_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]


def _has_id_column(df: pd.DataFrame) -> bool:
    """A column like order_id or email whose values are unique once exact copies are removed."""
    unique_rows = df.drop_duplicates()
    for c in unique_rows.columns:
        s = unique_rows[c].dropna()
        if len(s) and ID_NAME_RE.search(str(c)) and s.astype(STRING_DTYPE).str.strip().str.lower().is_unique:
            return True
    return False


def _email_columns(df: pd.DataFrame) -> list[str]:
    cols = []
    for c in _text_columns(df):
        s = df[c].dropna().astype(STRING_DTYPE).str.strip()
        if not len(s):
            continue
        share = float(s.str.fullmatch(EMAIL_RE).fillna(False).mean())
        if EMAIL_NAME_RE.search(c) or share >= 0.8:
            cols.append(c)
    return cols


def _category_columns(df: pd.DataFrame, exclude: set[str]) -> list[str]:
    """Text columns whose values repeat (city, status, gender...), where one spelling per word makes sense."""
    cols = []
    for c in _text_columns(df):
        if c in exclude:
            continue
        s = df[c].dropna().astype(STRING_DTYPE).str.strip()
        s = s[s != ""]
        if len(s) < 4:
            continue
        distinct = s.str.lower().nunique()
        if distinct <= 1000 and distinct <= 0.5 * len(s):
            cols.append(c)
    return cols


def well_cased(spelling: str) -> bool:
    """Starts with a capital and is not written in capitals (short acronyms such as "USA" are fine)."""
    letters = [ch for ch in spelling if ch.isalpha()]
    return spelling[:1].isupper() and (not spelling.isupper() or len(letters) <= 4)


def best_spellings(counts: dict[str, int]) -> dict[str, str]:
    """For each word written in more than one way, the spelling to use, keyed by its lowercase form.

    A properly capitalised spelling wins over all-lowercase or ALL-CAPS ones ("Lahore" over
    "lahore" and "LAHORE"), even when it is less common: counts are easily skewed by duplicate
    rows. Short acronyms such as "USA" count as properly capitalised. Among equals the most
    common spelling wins, then the first one given.
    """
    order = {spelling: i for i, spelling in enumerate(counts)}
    groups: dict[str, list[str]] = {}
    for spelling in counts:
        groups.setdefault(spelling.strip().lower(), []).append(spelling)

    def rank(spelling: str) -> tuple:
        return (not well_cased(spelling), -counts[spelling], spelling != spelling.title(), order[spelling])

    return {key: min(spellings, key=rank) for key, spellings in groups.items() if len(spellings) > 1}


def _spelling_mappings(s: pd.Series) -> list[dict]:
    """Map every word written in more than one way to one spelling (see best_spellings)."""
    text = s.dropna().astype(STRING_DTYPE).str.strip()
    text = text[text != ""]
    counts: dict[str, int] = {}
    for spelling in text.tolist():  # first-seen order, then counts
        counts[spelling] = counts.get(spelling, 0) + 1
    return [{"value": key, "to": to} for key, to in best_spellings(counts).items()]


def _placeholder_step(df: pd.DataFrame) -> dict | None:
    cols: list[str] = []
    tokens: set[str] = set()
    for c in _text_columns(df):
        stripped = df[c].dropna().astype(STRING_DTYPE).str.strip().str.lower()
        found = set(stripped[stripped.isin(profiling.PLACEHOLDER_TOKENS)].unique())
        if COUNTRY_NAME_RE.search(c):
            found.discard("na")  # NA is also Namibia's country code
        if found:
            cols.append(c)
            tokens |= found
    if not cols:
        return None
    return {"type": "map_values", "columns": cols, "ignore_case": True,
            "mappings": [{"value": t, "to": ""} for t in sorted(tokens)]}


def _date_candidates(df: pd.DataFrame) -> tuple[list[dict], list[str]]:
    ops: list[dict] = []
    decisions: list[str] = []
    for issue in profiling.detect_issues(df):
        if not str(issue["id"]).startswith("dates:"):
            continue
        col = issue["column"]
        summary = profiling.date_format_summary(df[col].dropna().astype(STRING_DTYPE))
        if summary["hint"] is None and any(_ambiguous_date(v) for v in df[col].dropna().astype(str).head(5000)):
            decisions.append(f'Dates in "{col}" could be day-first or month-first (e.g. 01/02/2026). '
                             "Convert them in Data types after checking with the client.")
            continue
        ops.append({"type": "convert_type", "columns": [col], "target": "datetime", "on_error": "abort",
                    "dayfirst": summary["hint"] == "day_first"})
    return ops, decisions


def _ambiguous_date(value: str) -> bool:
    m = profiling._DMY_RE.match(value)
    return bool(m) and int(m.group(1)) <= 12 and int(m.group(2)) <= 12 and m.group(1) != m.group(2)


def _candidates(df: pd.DataFrame) -> tuple[list[tuple[dict, str, bool, str | None]], list[str]]:
    """(operation, title, selected, note) in the order they should run, plus decisions left to a human."""
    out: list[tuple[dict, str, bool, str | None]] = []
    decisions: list[str] = []
    if len(df) and df.isna().all(axis=1).any():
        # A row without a single value carries no data; it also shows up as a duplicate and as missing values.
        out.append(({"type": "remove_empty", "target": "rows"}, "Remove completely empty rows", True, None))
    if df.duplicated().any():
        has_id = _has_id_column(df)
        out.append(({"type": "remove_duplicates", "keep": "first"}, "Remove exact duplicate rows", has_id,
                    None if has_id else "There is no ID or email column, so identical rows might be real repeat "
                                        "entries (for example two equal orders). Tick only if they are copies."))
    out.append(({"type": "trim_whitespace", "columns": []}, "Remove extra spaces", True, None))
    placeholder = _placeholder_step(df)
    if placeholder:
        out.append((placeholder, "Turn placeholder text (N/A, null, -) into empty cells", True, None))
    emails = _email_columns(df)
    if emails:
        out.append(({"type": "clean_email", "columns": emails, "lowercase": True, "fix_domains": False,
                     "on_invalid": "keep"}, f"Tidy email addresses in {', '.join(emails)}", True, None))
    countries = [c for c in _text_columns(df) if COUNTRY_NAME_RE.search(c)]
    if countries:
        out.append(({"type": "standardize_country", "columns": countries, "output": "name"},
                    f"Write country names the same way in {', '.join(countries)}", True, None))
    phones = [c for c in df.columns if PHONE_NAME_RE.search(str(c)) and str(c) not in countries]
    if phones and countries:
        out.append(({"type": "standardize_phone", "columns": [str(c) for c in phones], "region": "US",
                     "region_column": countries[0], "format": "international", "on_invalid": "keep"},
                    f'Format phone numbers in {", ".join(map(str, phones))} using each row\'s country', True, None))
    elif phones:
        decisions.append(f'Phone numbers in {", ".join(f"{c!r}" for c in phones)}: there is no country column, so '
                         "choose the country in Clean data → Contact details → Phone numbers.")
    for c in _category_columns(df, set(emails) | set(phones) | set(countries)):
        mappings = _spelling_mappings(df[c])
        if mappings:
            out.append(({"type": "map_values", "columns": [c], "ignore_case": True, "mappings": mappings},
                        f'Use one spelling for each value in "{c}"', True, None))
    date_ops, date_decisions = _date_candidates(df)
    out.extend((op, f'Write the dates in "{op["columns"][0]}" in one format', True, None) for op in date_ops)
    decisions.extend(date_decisions)
    for issue in profiling.detect_issues(df):
        if str(issue["id"]).startswith("amounts:"):
            col = issue["column"]
            out.append(({"type": "clean_numbers", "columns": [col], "decimal": "auto", "on_error": "abort"},
                        f'Turn the amounts in "{col}" into numbers', True, None))
    if any(str(c) != str(c).strip() for c in df.columns):
        # Last, because every step before it refers to the columns by their current names.
        out.append(({"type": "clean_column_names", "replace_spaces": False, "lowercase": False},
                    "Remove spaces around column names", True, None))
    return out, decisions


def _open_decisions(df: pd.DataFrame) -> list[str]:
    notes = []
    for issue in profiling.detect_issues(df):
        if str(issue["id"]).startswith(("missing:", "outliers:", "mixed:", "empty_col:")):
            notes.append(issue["title"])
    return notes


def plan(df: pd.DataFrame) -> dict:
    """Simulate every candidate in order and keep the ones that change something."""
    steps = []
    decisions: list[str] = []
    candidates, decisions = _candidates(df)
    work = df
    for i, (params, title, selected, note) in enumerate(candidates):
        op = _OPERATION.validate_python(params)
        try:
            result = run_operation(work, op)
        except Exception:  # a candidate that does not fit this data is simply not proposed
            continue
        if result.blocked:
            if op.type == "convert_type":
                decisions.append(f'Some dates in "{op.columns[0]}" could not be read. Check them in Data types.')
            elif op.type == "clean_numbers":
                decisions.append(f'Some values in "{op.columns[0]}" are not amounts. Check them in Data types → Clean numbers.')
            continue
        if not result.changed:
            continue
        if op.type == "clean_numbers" and result.warnings:
            # Mixed currencies or "1,250" that could mean 1.25: a person must decide, so it starts unticked.
            selected, note = False, result.warnings[0]
        steps.append({"id": f"step-{i + 1}", "title": title, "summary": result.summary, "label": LABELS[op.type],
                      "operation": op.model_dump(), "selected": selected, "note": note,
                      "warnings": result.warnings})
        if selected:
            work = result.df
    decisions.extend(_open_decisions(work))
    return {"steps": steps, "needs_decision": list(dict.fromkeys(decisions))}


# --------------------------------------------------------------------------- change report

def change_report(filename: str, original: pd.DataFrame, current: pd.DataFrame, steps: list[dict]) -> dict:
    """What was done to the file, what is marked for review and what is still open, plus a ready-to-send message."""
    review = []
    for step in steps:
        params = step["params"]
        name = params.get("column_name") if step["type"] in ("flag_rows", "near_duplicates") else None
        if name and name in current.columns and name not in [r["column"] for r in review]:
            review.append({"column": name, "rows": int(current[name].notna().sum())})
    open_items = _open_decisions(current)
    lines = ["Hi! Your cleaned file is attached. Here is what I did:", ""]
    lines += [f"• {s['summary']}" for s in steps] or ["• No changes were needed."]
    lines += ["", f"Rows: {len(original):,} → {len(current):,}. Columns: {original.shape[1]:,} → {current.shape[1]:,}."]
    if review:
        lines += ["", "Please review:"]
        lines += [f'• {r["rows"]:,} row{"s" if r["rows"] != 1 else ""} are marked in the "{r["column"]}" column.'
                  for r in review]
    if open_items:
        lines += ["", "Left for your decision (not changed):"]
        lines += [f"• {item}" for item in open_items[:10]]
    lines += ["", "Nothing else was changed or removed. Let me know if you would like any adjustments!"]
    return {
        "file": filename,
        "rows_before": len(original), "rows_after": len(current),
        "columns_before": original.shape[1], "columns_after": current.shape[1],
        "steps": [{"label": s["label"], "summary": s["summary"]} for s in steps],
        "review": review,
        "open_items": open_items,
        "message": "\n".join(lines),
    }
