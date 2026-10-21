"""Combine the working data with another file: append its rows, or join its columns (like VLOOKUP).

Like every cleaning operation this is a pure function: the working data and the
other file are never modified, and preview and apply run the same code.

Row numbers: rows of the working data keep their row numbers, so the
before/after comparison still lines up with the original upload. New rows
(appended rows, extra copies from a one-to-many join, unmatched rows of an
outer join) get new numbers after the highest one in use.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.core.errors import AppError
from app.schemas.operations import CombineFiles
from app.services.csv_loader import STRING_DTYPE

# A result larger than this is almost always a join on the wrong column (rows multiplied).
MAX_RESULT_ROWS = 5_000_000
MAX_RESULT_CELLS = 100_000_000
SAMPLE_ROWS = 20


@dataclass
class CombineContext:
    files: dict = field(default_factory=dict)   # file id -> sessions.AttachedFile
    index_start: int = 0                         # first row label free for new rows
    current_name: str = ""                       # file name of the working data


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}s"


def _v(n: int, one: str, many: str) -> str:
    """Verb that agrees with a count: _v(1, "has", "have")."""
    return one if n == 1 else many


def _names(cols) -> str:
    shown = [f'"{c}"' for c in list(cols)[:5]]
    more = len(cols) - len(shown)
    return ", ".join(shown) + (f" and {more} more" if more > 0 else "")


def _text(s: pd.Series) -> pd.Series:
    """A column as text, with dates written the same way as everywhere else in the app."""
    if pd.api.types.is_datetime64_any_dtype(s):
        out = s.dt.strftime("%Y-%m-%d %H:%M:%S").str.replace(" 00:00:00", "", regex=False)
        return out.astype(STRING_DTYPE)
    if isinstance(s.dtype, pd.StringDtype):
        return s
    return s.astype(STRING_DTYPE)


def _nullable(s: pd.Series) -> pd.Series:
    """Same values, in a type that can hold a missing value (numpy int/bool cannot)."""
    kind = getattr(s.dtype, "kind", None)
    if isinstance(s.dtype, np.dtype) and kind in "iu":
        return s.astype("Int64" if kind == "i" else "UInt64")
    if isinstance(s.dtype, np.dtype) and kind == "b":
        return s.astype("boolean")
    return s


def _missing(like: pd.Series, index: pd.Index) -> pd.Series:
    """An all-missing column of the same type as `like`."""
    return pd.Series(pd.NA, index=index, dtype=_nullable(like.iloc[:0]).dtype)


def _take(s: pd.Series, positions: np.ndarray, index: pd.Index) -> pd.Series:
    """Values at `positions` (-1 = missing), with the given row labels."""
    s = _nullable(s) if (positions < 0).any() else s
    values = s.array.take(positions, allow_fill=True)
    return pd.Series(values, index=index, name=s.name)


def _stack(top: pd.DataFrame, bottom: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Rows of `bottom` under `top`, columns matched by name (top's order first).

    A column missing on one side is empty there. When a column has different types in
    the two parts (e.g. numbers in one file, text in the other) it becomes text, so no
    value is lost or silently converted; those columns are returned for a warning.
    """
    columns = list(top.columns) + [c for c in bottom.columns if c not in top.columns]
    retyped: list[str] = []
    parts_top, parts_bottom = {}, {}
    for c in columns:
        a = top[c] if c in top.columns else None
        b = bottom[c] if c in bottom.columns else None
        if a is None:
            a = _missing(b, top.index)
        if b is None:
            b = _missing(a, bottom.index)
        a, b = _nullable(a), _nullable(b)
        if a.dtype != b.dtype:
            # Missing on one side only: keep the real column's type.
            if c not in top.columns:
                a = a.astype(b.dtype)
            elif c not in bottom.columns:
                b = b.astype(a.dtype)
            else:
                a, b = _text(a), _text(b)
                retyped.append(str(c))
        parts_top[c], parts_bottom[c] = a, b
    out = pd.concat([pd.DataFrame(parts_top, index=top.index), pd.DataFrame(parts_bottom, index=bottom.index)])
    return out[columns], retyped


def _key_text(s: pd.Series, loose: bool) -> pd.Series:
    t = _text(s)
    if loose:
        t = t.str.strip().str.replace(r"\s+", " ", regex=True).str.casefold()
    return t.mask((t == "").fillna(False).astype(bool), pd.NA)


def _row_keys(df: pd.DataFrame, cols: list[str], loose: bool) -> pd.Series:
    """One comparable key per row; missing when any key column is empty (empty keys never match)."""
    parts = [_key_text(df[c], loose) for c in cols]
    key = parts[0]
    for p in parts[1:]:
        key = key + "\x1f" + p  # missing in any part -> missing
    return key.reset_index(drop=True)


def _check_size(rows: int, columns: int) -> str | None:
    if rows > MAX_RESULT_ROWS or rows * max(columns, 1) > MAX_RESULT_CELLS:
        return (f"The result would have {rows:,} rows and {columns:,} columns, which is too large. "
                "Check the match columns: when a value appears many times in both files, rows multiply. "
                'Choose "Use the first match" or more specific match columns.')
    return None


def combine_files(df: pd.DataFrame, op: CombineFiles, ctx: CombineContext | None):
    from app.services.operations import OpResult  # avoid an import cycle

    ctx = ctx or CombineContext()
    attached = ctx.files.get(op.file_id)
    if attached is None:
        raise AppError("file_not_found", "The other file is no longer available.",
                       "Add the file again under Combine files, then preview again.", status=404)
    if op.mode == "append":
        return _append(df, attached, op, ctx, OpResult)
    return _join(df, attached, op, ctx, OpResult)


# --------------------------------------------------------------------------- append

def _append(df: pd.DataFrame, attached, op: CombineFiles, ctx: CombineContext, OpResult):
    other = attached.df
    name = attached.name
    common = [c for c in df.columns if c in other.columns]
    only_current = [str(c) for c in df.columns if c not in other.columns]
    only_other = [str(c) for c in other.columns if c not in df.columns]
    if op.source_column and (op.source_column in df.columns or op.source_column in other.columns):
        raise AppError("column_exists", f'Column "{op.source_column}" already exists.',
                       "Choose another name for the column that records the source file.")
    if not common and len(df.columns) and len(other.columns):
        return OpResult(df, f'"{name}" has no column names in common with your data.',
                        blocked=(f'None of the column names of "{name}" match your data, so its rows would not '
                                 "line up under the right columns. Rename the columns first (Organize columns) "
                                 "so the same information has the same name in both files."))
    blocked = _check_size(len(df) + len(other), len(df.columns) + len(only_other) + bool(op.source_column))
    if blocked:
        return OpResult(df, "The combined data would be too large.", blocked=blocked)
    if not len(other):
        return OpResult(df, f'"{name}" has no rows to add.')

    new_index = pd.RangeIndex(ctx.index_start, ctx.index_start + len(other))
    bottom = other.copy(deep=False)
    bottom.index = new_index
    top = df
    if op.source_column:
        top = df.copy(deep=False)
        top[op.source_column] = pd.Series(ctx.current_name or "working data", index=df.index, dtype=STRING_DTYPE)
        bottom[op.source_column] = pd.Series(name, index=new_index, dtype=STRING_DTYPE)
    out, retyped = _stack(top, bottom)

    summary = f'Added {_plural(len(other), "row")} from "{name}" below your data ({len(out):,} rows in total).'
    warnings = []
    if only_other:
        n = len(only_other)
        warnings.append(f'{_plural(n, "column")} {_v(n, "exists", "exist")} only in "{name}" and '
                        f'{_v(n, "was", "were")} added (empty for your existing rows): {_names(only_other)}.')
    if only_current:
        n = len(only_current)
        warnings.append(f'{_plural(n, "column")} of your data {_v(n, "is", "are")} not in "{name}" and '
                        f'{_v(n, "is", "are")} empty for the added rows: {_names(only_current)}.')
    if retyped:
        n = len(retyped)
        warnings.append(f"{_plural(n, 'column')} had different types in the two files and {_v(n, 'is', 'are')} "
                        f"now text, so no value was changed: {_names(retyped)}. Use Convert data type if needed.")
    added = list(only_other) + ([op.source_column] if op.source_column else [])
    details = {
        "rows_added": len(other),
        "added_index": list(new_index[:SAMPLE_ROWS]),
        "added_columns": added,
        "source_file": name,
        "columns_only_in_current": only_current,
        "columns_only_in_other": only_other,
        "retyped_columns": retyped,
    }
    # Only the new source column changes existing rows; added rows are counted as rows.
    cells = len(df) if op.source_column else 0
    if op.source_column:
        details["touched"] = [op.source_column]
    return OpResult(out, summary, cells_changed=cells, warnings=warnings, details=details)


# --------------------------------------------------------------------------- join

def _join(df: pd.DataFrame, attached, op: CombineFiles, ctx: CombineContext, OpResult):
    other = attached.df
    name = attached.name
    if not op.keys:
        raise AppError("no_keys", "Choose the column(s) that identify the same record in both files.",
                       'For example "email" in your data and "Email" in the other file.')
    left_cols = [k.left for k in op.keys]
    right_cols = [k.right for k in op.keys]
    missing_left = [c for c in left_cols if c not in df.columns]
    if missing_left:
        raise AppError("unknown_columns", f"Column(s) not found in your data: {', '.join(missing_left)}.", None)
    missing_right = [c for c in right_cols if c not in other.columns]
    if missing_right:
        raise AppError("unknown_columns", f'Column(s) not found in "{name}": {", ".join(missing_right)}.', None)
    if len(set(left_cols)) != len(left_cols) or len(set(right_cols)) != len(right_cols):
        raise AppError("duplicate_keys", "Each column can be used only once to match rows.", None)

    bring = list(dict.fromkeys(op.columns)) if op.columns else [c for c in other.columns if c not in right_cols]
    unknown = [c for c in bring if c not in other.columns]
    if unknown:
        raise AppError("unknown_columns", f'Column(s) not found in "{name}": {", ".join(unknown)}.', None)
    bring = [c for c in bring if c not in right_cols]
    if not bring and op.how == "left":
        raise AppError("nothing_to_bring", f'There are no columns to bring from "{name}".',
                       "Choose at least one column that is not a match column.")

    # Names of the brought columns in the result: never overwrite an existing column.
    used = set(map(str, df.columns))
    out_names: dict[str, str] = {}
    renamed: list[dict] = []
    for c in bring:
        new = str(c)
        if new in used:
            new = f"{c}{op.suffix}"
            n = 2
            while new in used:
                n += 1
                new = f"{c}{op.suffix}{n}"
            renamed.append({"before": str(c), "after": new})
        used.add(new)
        out_names[c] = new

    left_key = _row_keys(df, left_cols, op.loose_keys)
    right_key = _row_keys(other, right_cols, op.loose_keys)
    left_blank = int(left_key.isna().sum())
    right_valid = right_key.notna()
    dup_mask = right_key.duplicated(keep="first") & right_valid
    right_duplicate_keys = int(right_key[dup_mask].nunique())
    use_right = right_valid & ~dup_mask if op.duplicates == "first" else right_valid

    left_frame = pd.DataFrame({"k": left_key, "lpos": np.arange(len(df))})
    right_frame = pd.DataFrame({"k": right_key[use_right], "rpos": np.flatnonzero(use_right.to_numpy())})
    pairs = left_frame.merge(right_frame, on="k", how="left", sort=False)
    # A missing left key must not match anything (pandas would match missing with missing).
    pairs.loc[pairs["k"].isna(), "rpos"] = np.nan
    rpos = pairs["rpos"].fillna(-1).to_numpy(dtype=np.int64)
    lpos = pairs["lpos"].to_numpy(dtype=np.int64)
    matched = rpos >= 0

    matched_left = int(pd.Series(lpos[matched]).nunique())
    unmatched_left = len(df) - matched_left
    used_right = set(rpos[matched].tolist())
    if op.how == "outer":
        extra_right = [i for i in np.flatnonzero(right_valid.to_numpy() if op.duplicates == "all" else use_right.to_numpy())
                       if i not in used_right]
        # Rows of the other file without a key cannot match anything, so outer join adds them too.
        extra_right += np.flatnonzero(~right_valid.to_numpy()).tolist()
    else:
        extra_right = []

    keep = matched if op.how == "inner" else np.ones(len(pairs), dtype=bool)
    lpos_k, rpos_k = lpos[keep], rpos[keep]
    rows = int(keep.sum()) + len(extra_right)
    columns = len(df.columns) + len(bring)
    blocked = _check_size(rows, columns)
    if blocked:
        return OpResult(df, "The combined data would be too large.", blocked=blocked)

    # Row labels: the first copy of each row keeps its number; extra copies get new ones.
    labels = df.index.to_numpy()[lpos_k].copy()
    repeat = pd.Series(lpos_k).duplicated().to_numpy()
    n_new = int(repeat.sum())
    labels[repeat] = np.arange(ctx.index_start, ctx.index_start + n_new)
    index = pd.Index(labels.astype(np.int64))

    data = {c: _take(df[c], lpos_k, index) for c in df.columns}
    for c in bring:
        data[out_names[c]] = _take(other[c], rpos_k, index)
    out = pd.DataFrame(data, index=index)
    out.columns = [*df.columns, *[out_names[c] for c in bring]]

    added_index: list[int] = [int(i) for i in labels[repeat][:SAMPLE_ROWS]]
    if extra_right:
        start = ctx.index_start + n_new
        extra_index = pd.RangeIndex(start, start + len(extra_right))
        pos = np.asarray(extra_right, dtype=np.int64)
        tail = {}
        for lc, rc in zip(left_cols, right_cols):
            tail[lc] = _take(other[rc], pos, extra_index)
        for c in bring:
            tail[out_names[c]] = _take(other[c], pos, extra_index)
        out, retyped = _stack(out, pd.DataFrame(tail, index=extra_index))
        added_index += list(extra_index[: max(0, SAMPLE_ROWS - len(added_index))])
    else:
        retyped = []

    removed_rows = unmatched_left if op.how == "inner" else 0
    removed_index = [] if not removed_rows else [
        int(i) for i in df.index[np.setdiff1d(np.arange(len(df)), lpos[matched])][:SAMPLE_ROWS]]
    rows_added = n_new + len(extra_right)
    new_cols = [out_names[c] for c in bring]
    filled = int(sum(int(out[c].loc[out.index.isin(df.index)].notna().sum()) for c in new_cols))

    match_words = " + ".join(f'"{k.left}" = "{k.right}"' if k.left != k.right else f'"{k.left}"' for k in op.keys)
    summary = (f'Matched {matched_left:,} of {_plural(len(df), "row")} with "{name}" on {match_words}'
               + (f" and added {_plural(len(new_cols), 'column')}: {_names(new_cols)}." if new_cols else "."))
    if op.how == "inner" and removed_rows:
        summary += f" Removed {_plural(removed_rows, 'row')} that had no match."
    if extra_right:
        summary += f' Added {_plural(len(extra_right), "row")} from "{name}" that matched nothing.'
    warnings = []
    if unmatched_left and op.how == "left":
        warnings.append(f"{_plural(unmatched_left, 'row')} of your data found no match; "
                        f"{_v(unmatched_left, 'its', 'their')} new columns are empty.")
    if left_blank:
        warnings.append(f"{_plural(left_blank, 'row')} of your data {_v(left_blank, 'has', 'have')} an empty "
                        "match value and cannot match anything.")
    if right_duplicate_keys:
        if op.duplicates == "first":
            warnings.append(f'{_plural(right_duplicate_keys, "value")} {_v(right_duplicate_keys, "appears", "appear")} '
                            f'more than once in "{name}"; the first row with each value was used (like VLOOKUP).')
        else:
            warnings.append(f'{_plural(right_duplicate_keys, "value")} {_v(right_duplicate_keys, "appears", "appear")} '
                            f'more than once in "{name}", so {_plural(n_new, "extra row")} '
                            f'{_v(n_new, "was", "were")} added, one per extra match.')
    if renamed:
        warnings.append("Some columns already existed in your data, so the new ones were renamed: "
                        + ", ".join(f'"{r["before"]}" → "{r["after"]}"' for r in renamed[:5]) + ".")
    if retyped:
        warnings.append(f"{_plural(len(retyped), 'column')} had different types in the two files and "
                        f"{_v(len(retyped), 'is', 'are')} now text: {_names(retyped)}.")
    if matched_left == 0 and len(df):
        warnings.append("No row matched. Check that the match columns hold the same kind of value in both files.")

    details = {
        "source_file": name,
        "matched_rows": matched_left,
        "unmatched_rows": unmatched_left,
        "rows_added": rows_added,
        "added_index": added_index[:SAMPLE_ROWS],
        "added_columns": new_cols,
        "renamed_columns": renamed,
        "duplicate_keys_in_other": right_duplicate_keys,
        "blank_keys": left_blank,
        "retyped_columns": retyped,
        "touched": new_cols,
        "removed_index": removed_index,
    }
    return OpResult(out, summary, rows_removed=removed_rows, cells_changed=filled, warnings=warnings,
                    details=details)
