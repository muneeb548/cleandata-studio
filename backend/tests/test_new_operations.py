"""Split / merge columns, worldwide phone numbers and review flags."""

import pandas as pd
import pytest

from app.core.errors import AppError
from app.schemas.operations import FlagRows, MergeColumns, SplitColumn, StandardizePhone
from app.services import operations as ops

pytest.importorskip("phonenumbers")


def run(df, model, **params):
    return ops.run_operation(df, model(**params))


def values(series):
    return [None if pd.isna(v) else v for v in series.tolist()]


# ----------------------------------------------------------------- split

NAMES = "full_name,city\nAli Raza Khan,Lahore\n  Sara   Ahmed ,Karachi\nZoya,Islamabad\n,Quetta\n"


def test_split_name_from_start(frame):
    res = run(frame(NAMES), SplitColumn, type="split_column", column="full_name", names=["first", "last"])
    assert list(res.df.columns) == ["full_name", "first", "last", "city"]  # new columns sit next to the source
    assert values(res.df["first"]) == ["Ali", "Sara", "Zoya", None]
    assert values(res.df["last"]) == ["Raza Khan", "Ahmed", None, None]
    assert res.cells_changed == 5
    assert res.changed and not ops.is_destructive(SplitColumn(type="split_column", column="full_name", names=["a", "b"]))
    assert any("nothing to split" in w for w in res.warnings)


def test_split_name_from_end(frame):
    res = run(frame(NAMES), SplitColumn, type="split_column", column="full_name", names=["first", "last"],
              split_from="end")
    assert values(res.df["first"]) == ["Ali Raza", "Sara", None, None]
    assert values(res.df["last"]) == ["Khan", "Ahmed", "Zoya", None]


def test_split_on_custom_separator_and_remove_original(frame):
    df = frame('place\n"Lahore, Pakistan"\n"London,UK"\n')
    op = SplitColumn(type="split_column", column="place", separator=",", names=["city", "country"], keep_original=False)
    res = ops.run_operation(df, op)
    assert list(res.df.columns) == ["city", "country"]
    assert values(res.df["country"]) == ["Pakistan", "UK"]
    assert res.columns_removed == 1 and ops.is_destructive(op)
    assert list(df.columns) == ["place"]  # input untouched


def test_split_refuses_existing_name(frame):
    with pytest.raises(AppError) as exc:
        run(frame(NAMES), SplitColumn, type="split_column", column="full_name", names=["first", "city"])
    assert exc.value.code == "column_exists"


def test_split_can_reuse_the_original_name_when_it_is_removed(frame):
    res = run(frame(NAMES), SplitColumn, type="split_column", column="full_name", names=["full_name", "last"],
              keep_original=False)
    assert list(res.df.columns) == ["full_name", "last", "city"]
    assert values(res.df["full_name"]) == ["Ali", "Sara", "Zoya", None]
    assert res.columns_removed == 0 and "Replaced" in res.summary
    with pytest.raises(AppError):  # but never while the original is kept
        run(frame(NAMES), SplitColumn, type="split_column", column="full_name", names=["full_name", "last"])


def test_split_names_must_differ():
    with pytest.raises(ValueError):
        SplitColumn(type="split_column", column="a", names=["x", " x "])


# ----------------------------------------------------------------- merge

def test_merge_skips_missing_parts(frame):
    df = frame("first,last,age\nAli,Khan,30\nSara,,25\n,Ahmed,40\n,,1\n")
    res = run(df, MergeColumns, type="merge_columns", columns=["first", "last"], new_name="full_name")
    assert list(res.df.columns) == ["first", "last", "full_name", "age"]
    assert values(res.df["full_name"]) == ["Ali Khan", "Sara", "Ahmed", None]
    assert res.cells_changed == 3


def test_merge_with_separator_and_drop_originals(frame):
    df = frame("city,country\nLahore,Pakistan\nParis,France\n")
    op = MergeColumns(type="merge_columns", columns=["city", "country"], separator=", ", new_name="place",
                      keep_originals=False)
    res = ops.run_operation(df, op)
    assert list(res.df.columns) == ["place"]
    assert values(res.df["place"]) == ["Lahore, Pakistan", "Paris, France"]
    assert res.columns_removed == 2 and ops.is_destructive(op)


def test_merge_can_reuse_a_merged_name_when_originals_are_removed(frame):
    df = frame("id,first,last,age\n1,Ali,Khan,30\n")
    res = run(df, MergeColumns, type="merge_columns", columns=["first", "last"], new_name="first", keep_originals=False)
    assert list(res.df.columns) == ["id", "first", "age"]
    assert values(res.df["first"]) == ["Ali Khan"]
    assert res.columns_removed == 1
    with pytest.raises(AppError):
        run(df, MergeColumns, type="merge_columns", columns=["first", "last"], new_name="first")


# ----------------------------------------------------------------- phone numbers

PHONES = "phone\n(650) 253-0000\n650.253.0000\n+1 650 253 0000\n12345\n\n"


@pytest.mark.parametrize("fmt, expected", [
    ("national", "(650) 253-0000"),
    ("international", "+1 650-253-0000"),
    ("e164", "+16502530000"),
])
def test_us_phone_formats(frame, fmt, expected):
    res = run(frame(PHONES), StandardizePhone, type="standardize_phone", columns=["phone"], region="US", format=fmt)
    assert values(res.df["phone"])[:3] == [expected] * 3
    assert values(res.df["phone"])[3] == "12345"  # invalid values are kept by default ...
    assert res.details["invalid_counts"] == {"phone": 1}  # ... and reported
    assert res.warnings


def test_invalid_phone_can_be_set_missing(frame):
    res = run(frame(PHONES), StandardizePhone, type="standardize_phone", columns=["phone"], region="us",
              format="e164", on_invalid="set_missing")
    assert values(res.df["phone"])[3] is None


def test_pakistan_and_uk_numbers(frame):
    df = frame("pk,uk\n0300-1234567,020 7031 3000\n+92 300 1234567,+44 20 7031 3000\n923001234567,02070313000\n")
    pk = run(df, StandardizePhone, type="standardize_phone", columns=["pk"], region="PK", format="e164")
    assert values(pk.df["pk"]) == ["+923001234567"] * 3
    uk = run(df, StandardizePhone, type="standardize_phone", columns=["uk"], region="GB", format="e164")
    assert values(uk.df["uk"]) == ["+442070313000"] * 3


def test_numbers_with_country_code_work_with_any_region(frame):
    df = frame("p\n+44 20 7031 3000\n+1 650 253 0000\n")
    res = run(df, StandardizePhone, type="standardize_phone", columns=["p"], region="PK", format="e164")
    assert values(res.df["p"]) == ["+442070313000", "+16502530000"]


def test_excel_numeric_phone_column():
    df = pd.DataFrame({"p": [6502530000.0, None]})
    res = run(df, StandardizePhone, type="standardize_phone", columns=["p"], region="US", format="e164")
    assert values(res.df["p"]) == ["+16502530000", None]


def test_unknown_region_is_rejected(frame):
    with pytest.raises(AppError) as exc:
        run(frame(PHONES), StandardizePhone, type="standardize_phone", columns=["phone"], region="ZZ")
    assert exc.value.code == "unknown_region"


def test_region_must_be_two_letters():
    with pytest.raises(ValueError):
        StandardizePhone(type="standardize_phone", columns=["p"], region="USA")


# ----------------------------------------------------------------- review flags

PEOPLE = (
    "name,email,phone,amount\n"
    "Ali,ali@example.com,+1 650 253 0000,100\n"
    "Sara,sara@example,12345,abc\n"
    ",ALI@example.com ,,50\n"
)


def test_flag_rows_combines_reasons(frame):
    df = frame(PEOPLE)
    res = run(df, FlagRows, type="flag_rows", rules=[
        {"column": "name", "check": "missing"},
        {"column": "email", "check": "invalid_email"},
        {"column": "email", "check": "duplicate_value"},
        {"column": "phone", "check": "invalid_phone"},
        {"column": "amount", "check": "not_number"},
    ])
    flags = values(res.df["needs_review"])
    assert flags[0] == "Repeated email"
    assert flags[1] == "Invalid email in email; Invalid phone in phone; Not a number in amount"
    assert flags[2] == "Missing name; Repeated email"
    assert res.rows_removed == 0 and res.cells_changed == 3
    assert list(df.columns) == ["name", "email", "phone", "amount"]  # input untouched
    assert values(res.df["email"]) == values(df["email"])  # data itself is not changed


def test_flag_rows_with_nothing_to_flag(frame):
    res = run(frame("a\nx\ny\n"), FlagRows, type="flag_rows", rules=[{"column": "a", "check": "missing"}])
    assert not res.changed
    assert "needs_review" not in res.df.columns


def test_flag_rows_replaces_existing_review_column(frame):
    df = frame("a,needs_review\n,old\nx,old\n")
    res = run(df, FlagRows, type="flag_rows", rules=[{"column": "a", "check": "missing"}])
    assert values(res.df["needs_review"]) == ["Missing a", None]
    assert res.warnings


def test_flag_phone_uses_region_for_local_numbers(frame):
    df = frame("p\n(650) 253-0000\n")
    no_region = run(df, FlagRows, type="flag_rows", rules=[{"column": "p", "check": "invalid_phone"}])
    assert values(no_region.df["needs_review"]) == ["Invalid phone in p"]
    with_region = run(df, FlagRows, type="flag_rows", rules=[{"column": "p", "check": "invalid_phone", "region": "US"}])
    assert not with_region.changed


def test_flag_column_cannot_be_a_checked_column(frame):
    with pytest.raises(AppError):
        run(frame("a\n\n"), FlagRows, type="flag_rows", rules=[{"column": "a", "check": "missing"}], column_name="a")


# ----------------------------------------------------------------- through the workspace

def test_added_columns_show_in_preview_and_compare(frame, fresh_store):
    from app.services import workspace

    from .conftest import preview_apply

    df = frame(NAMES)
    session, _ = fresh_store.create(filename="n.csv", file_size=1, encoding="utf-8", delimiter=",",
                                    import_warnings=[], original=df)
    op = SplitColumn(type="split_column", column="full_name", names=["first", "last"])
    preview = workspace.preview_operation(session, op)
    samples = preview["changes"]["cell_samples"]
    assert {"row": 1, "column": "first", "before": None, "after": "Ali"} in samples
    result = preview_apply(session, op)
    assert result["applied"] and result["columns_after"] == 4
    changed = workspace.compare_rows(session, changes_only=True)
    assert changed["total_rows"] == 3  # the empty-name row gained no values
