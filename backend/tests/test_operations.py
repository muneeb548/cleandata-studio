import pandas as pd
import pytest

from app.core.errors import AppError
from app.services import operations as ops

from .conftest import MESSY_CSV


def run(df, **params):
    model = {
        "remove_duplicates": ops.RemoveDuplicates,
        "missing_values": ops.MissingValues,
        "trim_whitespace": ops.TrimWhitespace,
        "standardize_text": ops.StandardizeText,
        "clean_column_names": ops.CleanColumnNames,
        "convert_type": ops.ConvertType,
        "remove_empty": ops.RemoveEmpty,
        "find_replace": ops.FindReplace,
        "split_column": ops.SplitColumn,
        "merge_columns": ops.MergeColumns,
        "standardize_phone": ops.StandardizePhone,
        "flag_rows": ops.FlagRows,
    }[params["type"]]
    return ops.run_operation(df, model(**params))


# ----------------------------------------------------------------- duplicates

def test_remove_duplicates_keep_first(frame):
    df = frame(MESSY_CSV)
    res = run(df, type="remove_duplicates", keep="first")
    assert res.rows_removed == 1
    assert len(res.df) == 5
    assert 1 in res.df.index and 2 not in res.df.index
    assert len(df) == 6  # input untouched


def test_remove_duplicates_keep_last(frame):
    res = run(frame(MESSY_CSV), type="remove_duplicates", keep="last")
    assert 2 in res.df.index and 1 not in res.df.index


def test_no_duplicates_reports_no_change(frame):
    res = run(frame("a\n1\n2\n"), type="remove_duplicates")
    assert not res.changed


def test_duplicates_treat_missing_as_equal(frame):
    res = run(frame("a,b\n1,\n1,\n"), type="remove_duplicates")
    assert res.rows_removed == 1


# ----------------------------------------------------------------- missing values

def test_fill_mean_numeric_text_column(frame):
    df = frame("a\n1\n\n4\n")
    res = run(df, type="missing_values", strategy="fill_mean", columns=["a"])
    assert res.df["a"].tolist() == ["1", "2.5", "4"]
    assert res.cells_changed == 1


def test_fill_median(frame):
    res = run(frame("a\n1\n\n3\n100\n"), type="missing_values", strategy="fill_median", columns=["a"])
    assert res.df.loc[1, "a"] == "3"


def test_mean_rejected_for_text_columns(frame):
    with pytest.raises(AppError) as exc:
        run(frame(MESSY_CSV), type="missing_values", strategy="fill_mean", columns=["City", "Age"])
    assert exc.value.code == "not_numeric"


def test_mean_on_all_missing_column_rejected(frame):
    df = frame("a,b\n,1\n,2\n")
    df["a"] = df["a"].astype("Float64")
    with pytest.raises(AppError):
        run(df, type="missing_values", strategy="fill_mean", columns=["a"])


def test_fill_mean_on_integer_dtype_promotes_to_decimal(frame):
    df = frame("a\n1\n\n2\n")
    df["a"] = pd.to_numeric(df["a"]).astype("Int64")
    res = run(df, type="missing_values", strategy="fill_mean", columns=["a"])
    assert str(res.df["a"].dtype) == "Float64"
    assert res.df.loc[1, "a"] == 1.5
    assert res.warnings


def test_fill_constant_only_selected_columns(frame):
    df = frame("a,b\n,\nx,y\n")
    res = run(df, type="missing_values", strategy="fill_constant", columns=["a"], value="Unknown")
    assert res.df.loc[0, "a"] == "Unknown"
    assert pd.isna(res.df.loc[0, "b"])  # never touched


def test_fill_constant_requires_value(frame):
    with pytest.raises(AppError):
        run(frame("a\n\n"), type="missing_values", strategy="fill_constant", columns=["a"], value="")


def test_fill_constant_text_into_numeric_dtype_rejected(frame):
    df = frame("a,b\n1,x\n,y\n")
    df["a"] = df["a"].astype("Float64")
    with pytest.raises(AppError) as exc:
        run(df, type="missing_values", strategy="fill_constant", columns=["a"], value="n/a")
    assert exc.value.code == "invalid_fill"


def test_drop_rows_with_missing(frame):
    res = run(frame(MESSY_CSV), type="missing_values", strategy="drop_rows", columns=["Age"])
    assert res.rows_removed == 2
    assert res.df["Age"].isna().sum() == 0


def test_drop_columns_with_missing(frame):
    res = run(frame(MESSY_CSV), type="missing_values", strategy="drop_columns", columns=["Age", "City"])
    assert list(res.df.columns) == ["Name ", "City", "Salary", "Joined"]
    assert res.columns_removed == 1
    assert res.warnings  # City kept because it had nothing missing


def test_missing_values_requires_columns(frame):
    with pytest.raises(AppError) as exc:
        run(frame("a\n\n"), type="missing_values", strategy="drop_rows", columns=[])
    assert exc.value.code == "no_columns"


def test_unknown_column_rejected(frame):
    with pytest.raises(AppError) as exc:
        run(frame("a\n1\n"), type="missing_values", strategy="drop_rows", columns=["nope"])
    assert exc.value.code == "unknown_columns"


# ----------------------------------------------------------------- whitespace & text

def test_trim_whitespace_preserves_internal_spaces(frame):
    df = frame('a,b\n"  New   York ",x\n"   ",y\n')
    res = run(df, type="trim_whitespace")
    assert res.df.loc[0, "a"] == "New   York"
    assert pd.isna(res.df.loc[1, "a"])
    assert res.cells_changed == 2


def test_trim_selected_columns_only(frame):
    df = frame("a,b\n x , y \n")
    res = run(df, type="trim_whitespace", columns=["a"])
    assert res.df.loc[0, "a"] == "x"
    assert res.df.loc[0, "b"] == " y "


def test_standardize_text_cases(frame):
    df = frame("c,k\nlahore,1\nKARACHI,2\n,3\n")
    assert run(df, type="standardize_text", columns=["c"], case="title").df["c"].tolist()[:2] == ["Lahore", "Karachi"]
    assert run(df, type="standardize_text", columns=["c"], case="upper").df.loc[0, "c"] == "LAHORE"
    lower = run(df, type="standardize_text", columns=["c"], case="lower")
    assert lower.df.loc[1, "c"] == "karachi"
    assert pd.isna(lower.df.loc[2, "c"])  # missing values preserved


def test_standardize_rejects_non_text(frame):
    df = frame("n\n1\n")
    df["n"] = df["n"].astype("Int64")
    with pytest.raises(AppError):
        run(df, type="standardize_text", columns=["n"], case="lower")


def test_unicode_case_conversion(frame):
    res = run(frame("c\nÉCOLE\n"), type="standardize_text", columns=["c"], case="lower")
    assert res.df.loc[0, "c"] == "école"


# ----------------------------------------------------------------- column names

def test_clean_column_names():
    assert ops.proposed_column_names(["  First Name ", "Age"], True, True) == ["first_name", "age"]


def test_clean_column_names_avoids_collisions():
    names = ops.proposed_column_names(["a b", "a_b", "A B"], True, True)
    assert names == ["a_b", "a_b_2", "a_b_3"]
    assert len(set(names)) == 3


def test_clean_column_names_operation(frame):
    res = run(frame(MESSY_CSV), type="clean_column_names", replace_spaces=True, lowercase=True)
    assert list(res.df.columns) == ["name", "city", "age", "salary", "joined"]
    assert res.changed
    assert res.details["mapping"][0] == {"before": "Name ", "after": "name"}


def test_special_characters_in_names():
    assert ops.proposed_column_names(["Price ($)", "  "], True, False) == ["Price_($)", "column_2"]


# ----------------------------------------------------------------- type conversion

def test_numeric_conversion(frame):
    res = run(frame("a\n1\n2\n\n"), type="convert_type", columns=["a"], target="integer")
    assert str(res.df["a"].dtype) == "Int64"
    assert res.df["a"].tolist()[:2] == [1, 2]
    assert res.blocked is None


def test_invalid_conversion_blocks_by_default(frame):
    df = frame("a\n1\nabc\n2.5\n")
    res = run(df, type="convert_type", columns=["a"], target="integer")
    assert res.blocked
    assert res.details["invalid_counts"] == {"a": 2}
    assert {s["value"] for s in res.details["invalid_samples"]} == {"abc", "2.5"}
    assert res.df["a"].tolist() == df["a"].tolist()


def test_invalid_conversion_set_missing_is_reported(frame):
    res = run(frame("a\n1\nabc\n"), type="convert_type", columns=["a"], target="float", on_error="set_missing")
    assert res.blocked is None
    assert pd.isna(res.df.loc[1, "a"])
    assert res.warnings and "invalid" in res.summary


def test_datetime_conversion_and_invalid_dates(frame):
    df = frame("d\n2024-01-05\nnot a date\n2024-02-30\n")
    res = run(df, type="convert_type", columns=["d"], target="datetime", on_error="set_missing")
    assert pd.api.types.is_datetime64_any_dtype(res.df["d"])
    assert res.df.loc[0, "d"] == pd.Timestamp("2024-01-05")
    assert res.details["invalid_counts"] == {"d": 2}


def test_datetime_with_explicit_format(frame):
    res = run(frame("d\n05/01/2024\n"), type="convert_type", columns=["d"], target="datetime", date_format="%d/%m/%Y")
    assert res.df.loc[0, "d"] == pd.Timestamp("2024-01-05")


def test_convert_to_string(frame):
    df = frame("a\n1\n")
    df["a"] = df["a"].astype("Int64")
    res = run(df, type="convert_type", columns=["a"], target="string")
    assert pd.api.types.is_string_dtype(res.df["a"])
    assert res.changed


def test_mixed_types_conversion(frame):
    res = run(frame("a\n1\ntwo\n3\n"), type="convert_type", columns=["a"], target="integer", on_error="set_missing")
    assert res.df["a"].tolist()[0] == 1 and pd.isna(res.df["a"].tolist()[1])


# ----------------------------------------------------------------- empty rows / columns, find replace

def test_remove_empty_rows_and_columns(frame):
    df = frame("a,b,c\n1,,x\n,,\n2,,y\n")
    res = run(df, type="remove_empty", target="both")
    assert list(res.df.columns) == ["a", "c"]
    assert len(res.df) == 2
    assert res.rows_removed == 1 and res.columns_removed == 1


def test_remove_empty_only_columns(frame):
    res = run(frame("a,b\n1,\n,\n"), type="remove_empty", target="columns")
    assert list(res.df.columns) == ["a"]
    assert len(res.df) == 2


def test_find_replace_exact_to_missing(frame):
    res = run(frame("a\nN/A\nn/a\nok\n"), type="find_replace", columns=["a"], find="N/A", replace="",
              case_sensitive=False)
    assert res.df["a"].isna().sum() == 2
    assert res.cells_changed == 2


def test_find_replace_contains(frame):
    res = run(frame("a\nfoo-bar\nbar\n"), type="find_replace", columns=["a"], find="-", replace=" ",
              match="contains")
    assert res.df.loc[0, "a"] == "foo bar"
    assert res.cells_changed == 1


def test_find_replace_special_characters_are_literal(frame):
    res = run(frame("a\n$5.00 (approx)\n"), type="find_replace", columns=["a"], find="(approx)",
              replace="\\1", match="contains")
    assert res.df.loc[0, "a"] == "$5.00 \\1"


# ----------------------------------------------------------------- outliers

def test_outlier_detection_does_not_modify(frame):
    df = frame(MESSY_CSV)
    before = df.copy()
    rep = ops.outlier_report(df, "Salary")
    assert rep["count"] == 1
    assert rep["outliers"][0]["value"] == "1000000"
    assert rep["outliers"][0]["position"] == "above"
    pd.testing.assert_frame_equal(df, before)


def test_outliers_rejected_for_text(frame):
    with pytest.raises(AppError):
        ops.outlier_report(frame(MESSY_CSV), "City")
