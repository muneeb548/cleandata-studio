"""Cheap memory estimates for DataFrames, used to keep undo history within budget.

With pandas copy-on-write, a cleaning step that changes one column shares every
other column with the previous version, so each history step is charged only
for the columns it actually created.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SAMPLE_ROWS = 5000


def _buffer(s: pd.Series):
    arr = s.array
    for attr in ("_ndarray", "_data"):
        buf = getattr(arr, attr, None)
        if isinstance(buf, np.ndarray):
            return buf
    try:
        return s.to_numpy(copy=False)
    except (TypeError, ValueError):
        return None


def column_bytes(s: pd.Series) -> int:
    n = len(s)
    if n == 0:
        return 0
    if n <= SAMPLE_ROWS:
        return int(s.memory_usage(deep=True, index=False))
    sample = s.iloc[np.linspace(0, n - 1, SAMPLE_ROWS).astype(int)]
    return int(sample.memory_usage(deep=True, index=False) / SAMPLE_ROWS * n)


def frame_bytes(df: pd.DataFrame) -> int:
    return sum(column_bytes(df.iloc[:, i]) for i in range(df.shape[1]))


def new_bytes(df: pd.DataFrame, previous: pd.DataFrame | None) -> int:
    """Bytes of the columns in `df` that do not share memory with `previous`."""
    if previous is None:
        return frame_bytes(df)
    prev_bufs = [b for b in (_buffer(previous.iloc[:, i]) for i in range(previous.shape[1])) if b is not None]
    total = 0
    for i in range(df.shape[1]):
        col = df.iloc[:, i]
        buf = _buffer(col)
        if buf is not None and any(np.may_share_memory(buf, pb) for pb in prev_bufs):
            continue
        total += column_bytes(col)
    return total
