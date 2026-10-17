"""Convert pandas/NumPy values into JSON-safe Python values (NaN, NA, NaT, numpy types, infinities)."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def to_jsonable(value: Any) -> Any:
    """Convert a pandas/numpy cell into something json.dumps can handle."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        if pd.isna(value):
            return None
        if value.hour == 0 and value.minute == 0 and value.second == 0 and value.microsecond == 0:
            return value.strftime("%Y-%m-%d")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        f = float(value)
        if math.isnan(f):
            return None
        if math.isinf(f):
            return "Infinity" if f > 0 else "-Infinity"
        return f
    if isinstance(value, np.bool_):
        return bool(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def frame_rows(df: pd.DataFrame) -> list[list[Any]]:
    return [[to_jsonable(v) for v in row] for row in df.itertuples(index=False, name=None)]