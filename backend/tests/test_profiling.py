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


# --------------------------------------------------------------- mixed date formats

def _issue(df, issue_id):
    return next((i for i in profiling.detect_issues(df) if i["id"] == issue_id), None)


def test_mixed_date_formats_are_flagged(frame):
    df = frame(
        "order_date\n2026-01-15\n15/01/2026\nJan 15 2026\n2026/01/15\n15/01/2026\n2026-01-15\n"
    )
    issue = _issue(df, "dates:order_date")
    assert issue is not None
    assert issue["severity"] == "medium"
    assert issue["title"] == 'Mixed date formats in "order_date"'
    assert issue["count"] == 4
    assert issue["suggested_operation"] == "convert_type"
    assert issue["example"] == "2026-01-15"  # a real value from the data
    assert '"Jan 15 2026"' in issue["description"] or '"15/01/2026"' in issue["description"]


def test_month_name_dates_are_recognised(frame):
    df = frame('d\n"January 15, 2026"\n"March 3, 2026"\n"December 31, 2025"\n')
    issue = _issue(df, "dates:d")
    assert issue is not None
    assert issue["severity"] == "low"  # one consistent format
    assert issue["title"] == '"d" looks like dates stored as text'


def test_single_numeric_format_keeps_low_severity(frame):
    df = frame("d\n2024-01-05\n2024-02-10\n2024-03-01\n")
    issue = _issue(df, "dates:d")
    assert issue is not None and issue["severity"] == "low"


def test_text_with_month_words_is_not_a_date(frame):
    df = frame("name\nMay Khan\nJune Ali\nMaybe 5 2026\nMarch Brown\n")
    assert _issue(df, "dates:name") is None


def test_day_first_hint(frame):
    df = frame("d\n15/01/2026\n03/02/2026\n2026-01-15\n")
    issue = _issue(df, "dates:d")
    assert issue is not None
    assert "Day comes first" in issue["description"]
    assert "tick" in issue["description"] and "unticked" not in issue["description"]


def test_month_first_hint(frame):
    df = frame("d\n01/15/2026\n02/03/2026\n2026-01-15\n")
    issue = _issue(df, "dates:d")
    assert issue is not None
    assert "unticked" in issue["description"]


def test_ambiguous_dates_give_no_hint(frame):
    df = frame("d\n01/02/2026\n03/04/2026\n2026-01-15\n")
    issue = _issue(df, "dates:d")
    assert issue is not None
    assert "Day comes first" not in issue["description"]


def test_ordinal_suffixes_count_as_one_format():
    s = pd.Series(["Mar 3rd 2026", "Mar 15th 2026", "Mar 1 2026"])
    assert profiling.date_format_summary(s)["formats"] == 1


# --------------------------------------------------------------- contact details and amounts

CONTACTS = (
    "email,phone,country,amount\n"
    '" ALI@Gmail.com ",(650) 253-0000,USA,"$1,250.00"\n'
    "sara@example,0300-1234567,Pakistan,\"Rs 1,25,000\"\n"
    "omar@gmail.com,+44 20 7031 3000,U.K.,99.50\n"
    "zoya@gmail.com,650.253.0000,United States,\"1.234,56 €\"\n"
)


def test_email_issue_counts_untidy_and_invalid(frame):
    issue = _issue(frame(CONTACTS), "emails:email")
    assert issue["suggested_operation"] == "clean_email" and issue["severity"] == "medium"
    assert issue["count"] == 2 and issue["example"] == "sara@example"
    assert "1 address with capitals" in issue["description"]


def test_tidy_emails_raise_no_issue(frame):
    assert _issue(frame("email\na@b.com\nc@d.org\n"), "emails:email") is None


def test_phone_layouts_issue(frame):
    issue = _issue(frame(CONTACTS), "phones:phone")
    assert issue["suggested_operation"] == "standardize_phone" and issue["count"] == 4


def test_international_phones_from_different_countries_are_fine(frame):
    df = frame("phone\n+1 650-253-0000\n+44 20 7031 3000\n+92 300 1234567\n")
    assert _issue(df, "phones:phone") is None


def test_country_names_issue(frame):
    issue = _issue(frame(CONTACTS), "countries:country")
    assert issue["suggested_operation"] == "standardize_country"
    assert issue["count"] == 2  # USA and U.K.; "Pakistan" and "United States" are already full names


def test_amounts_stored_as_text(frame):
    issue = _issue(frame(CONTACTS), "amounts:amount")
    assert issue["suggested_operation"] == "clean_numbers" and issue["example"] == "$1,250.00"


def test_plain_words_are_not_amounts(frame):
    assert _issue(frame("city\nLahore\nKarachi\nLondon\n"), "amounts:city") is None


def test_health_counts_placeholders_as_missing(frame):
    df = frame("id,status,city\n1,N/A,Lahore\n2,null,Lahore \n3,paid,   \n4,paid,Karachi\n")
    profile = profiling.full_profile(df)
    health = profile["health"]
    assert profile["stats"]["completeness"] == 100.0  # no truly empty cell…
    assert health["looks_empty_cells"] == 3  # …but 2 placeholders and 1 space-only cell
    assert health["real_completeness"] == round(9 / 12 * 100, 2)
    assert health["needs_cleaning"] is True
    cols = {c["name"]: c for c in profile["columns"]}
    assert cols["status"]["looks_empty"] == 2 and cols["status"]["completeness"] == 50.0
    assert cols["city"]["looks_empty"] == 1 and cols["city"]["issues"] >= 2  # spaces + blank
    assert cols["id"]["issues"] == 0 and cols["id"]["completeness"] == 100.0
    assert health["columns_with_issues"] == 2 and health["issues"] == 3 and health["notes"] == 0


def test_health_of_clean_data(frame):
    profile = profiling.full_profile(frame("id,name\n1,Ali\n2,Sara\n"))
    assert profile["health"] == {**profile["health"], "looks_empty_cells": 0, "real_completeness": 100.0,
                                 "needs_cleaning": False}


def test_more_placeholders_are_recognised(frame):
    df = frame('signup,score\n2024-01-05,1\nnot available,#DIV/0!\n(blank),#VALUE!\n2024-02-01,4\n')
    profile = profiling.full_profile(df)
    cols = {c["name"]: c for c in profile["columns"]}
    assert cols["signup"]["looks_empty"] == 2 and cols["score"]["looks_empty"] == 2
