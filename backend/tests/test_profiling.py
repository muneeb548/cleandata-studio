import json

import numpy as np
import pandas as pd

from app.services import profiling

from .conftest import MESSY_CSV


def test_missing_values_detection(frame):
    df = frame(MESSY_CSV)
    stats = profiling.basic_stats(df)
    assert stats["rows"] == 6
    assert stats["columns"] == 5
    assert stats["missing_cells"] == 3  # two Age, one Salary
    assert stats["columns_with_missing"] == 2
    assert stats["duplicate_rows"] == 1
    assert stats["completeness"] == round(27 / 30 * 100, 2)


def test_zero_cells_completeness_is_safe(frame):
    df = frame("a,b\n")
    stats = profiling.basic_stats(df)
    assert stats["total_cells"] == 0
    assert stats["completeness"] is None
    assert profiling.detect_issues(df)[0]["id"] == "no_rows"


def test_one_row_dataset(frame):
    stats = profiling.basic_stats(frame("a,b\n1,2\n"))
    assert stats == {**stats, "rows": 1, "duplicate_rows": 0, "completeness": 100.0}


def test_logical_types(frame):
    df = frame("i,f,t,z,e,m\n1,1.5,x,007,,5\n2,2.25,y,010,,abc\n")
    types = {p["name"]: p["type"] for p in profiling.column_profiles(df)}
    assert types == {"i": "integer", "f": "decimal", "t": "text", "z": "text", "e": "empty", "m": "text"}


def test_thousands_separator_but_not_decimal_comma():
    nums = profiling.numeric_view(pd.Series(["1,250", "1,5", "3"], dtype="string"))
    assert nums.iloc[0] == 1250
    assert np.isnan(nums.iloc[1])
    assert nums.iloc[2] == 3


def test_issue_detection(frame):
    df = frame(MESSY_CSV)
    ids = {i["id"] for i in profiling.detect_issues(df)}
    assert "duplicates" in ids
    assert "missing:Age" in ids
    assert "whitespace:Name " in ids
    assert "case:City" in ids
    assert "column_names" in ids
    assert "outliers:Salary" in ids


def test_placeholders_and_all_missing_column(frame):
    df = frame("a,b,c\nN/A,,1\nnull,,2\nx,,3\n")
    ids = {i["id"] for i in profiling.detect_issues(df)}
    assert "placeholder:a" in ids
    assert "empty_col:b" in ids


def test_mixed_types_detected(frame):
    df = frame("v\n" + "\n".join(["1", "2", "3", "4", "5", "6", "7", "8", "9", "oops"]) + "\n")
    ids = {i["id"] for i in profiling.detect_issues(df)}
    assert "mixed:v" in ids


def test_profile_is_json_serialisable(frame):
    df = frame(MESSY_CSV)
    df["Salary"] = profiling.numeric_view(df["Salary"]).astype("Float64")
    df.loc[0, "Salary"] = np.inf
    json.dumps(profiling.full_profile(df))
    json.dumps(profiling.frame_rows(df))


def test_to_jsonable_handles_special_values():
    assert profiling.to_jsonable(pd.NA) is None
    assert profiling.to_jsonable(float("nan")) is None
    assert profiling.to_jsonable(float("inf")) == "Infinity"
    assert profiling.to_jsonable(pd.Timestamp("2024-01-05")) == "2024-01-05"
    assert profiling.to_jsonable(np.int64(3)) == 3
