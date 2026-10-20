"""Chat with your data: the AI's query plan is checked and computed by the app."""

import pandas as pd
import pytest

from app.core.errors import AppError
from app.services import ask as q

from .conftest import load

CSV = (
    "name,email,city,amount,joined\n"
    "Ali,a@x.com,Lahore,100,2024-01-05\n"
    "Sara,s@x.com,lahore ,250,2024-03-01\n"
    "John,j@x.com,Karachi,$1,2023-12-01\n"
    "Mia,,Karachi,50,2024-06-01\n"
    "Zed,z@x.com,,10,\n"
)


@pytest.fixture
def df():
    return load(CSV).df


def plan(**kw):
    base = {"possible": True, "reply": "", "description": "Result", "filters": [], "group_by": [],
            "metric": "count_rows", "metric_column": "", "sort": "none", "limit": 20}
    return {**base, **kw}


def answer(df, **kw):
    return q.run(df, q.check_plan(df, plan(**kw)))


def test_count_per_group_sorted(df):
    res = answer(df, group_by=["city"], sort="desc", description="Customers per city")
    assert res["columns"] == ["city", "Rows"]
    assert res["rows"][0] == ["Karachi", 2]
    assert ["(missing)", 1] in res["rows"]
    assert res["answer"] == "Customers per city: Karachi (2)"
    assert any("capital letters" in n for n in res["notes"])  # Lahore / lahore


def test_sum_reports_values_that_are_not_numbers(df):
    res = answer(df, metric="sum", metric_column="amount", description="Total amount")
    assert res["rows"] == [[410.0]] and res["answer"] == "Total amount: 410"
    assert res["notes"] and "1 value is" in res["notes"][0]


@pytest.mark.parametrize("op,value,expected", [
    ("equals", "LAHORE", 2),          # ignores capitals and outer spaces
    ("not_equals", "karachi", 3),
    ("contains", "ka", 2),
    ("greater_than", "60", 2),        # numbers as numbers
    ("less_than", "2024-02-01", 2),   # dates as dates
    ("is_missing", "", 1),
    ("is_not_missing", "", 4),
])
def test_filters(df, op, value, expected):
    column = {"greater_than": "amount", "less_than": "joined", "is_missing": "email", "is_not_missing": "city"}.get(op, "city")
    res = answer(df, filters=[{"column": column, "op": op, "value": value}])
    assert res["rows_matched"] == expected


def test_grouped_average_with_filter(df):
    res = answer(df, group_by=["city"], metric="mean", metric_column="amount", sort="desc",
                 filters=[{"column": "joined", "op": "greater_than", "value": "2024-01-01"}])
    assert res["rows"] == [["lahore", 250.0], ["Lahore", 100.0], ["Karachi", 50.0]]


def test_distinct_and_missing(df):
    assert answer(df, metric="count_distinct", metric_column="city")["rows"] == [[3]]
    assert answer(df, metric="count_missing", metric_column="email")["rows"] == [[1]]


def test_two_group_columns_and_limit(df):
    res = answer(df, group_by=["city", "name"], limit=2, sort="asc")
    assert len(res["rows"]) == 2 and res["total_groups"] == 5
    assert any("Showing 2 of 5" in n for n in res["notes"])


@pytest.mark.parametrize("bad,message", [
    (plan(group_by=["nope"]), "does not exist"),
    (plan(metric="drop_table"), "does not support"),
    (plan(filters=[{"column": "city", "op": "exec", "value": "x"}]), "does not understand"),
    (plan(metric="sum", metric_column="missing_col"), "does not exist"),
    (plan(group_by=["city", "city"]), "twice"),
])
def test_bad_plans_are_refused(df, bad, message):
    with pytest.raises(AppError) as err:
        q.check_plan(df, bad)
    assert message in err.value.message and err.value.status == 422


def test_numbers_needed_for_sum(df):
    with pytest.raises(AppError, match="no numbers"):
        answer(df, metric="sum", metric_column="name")
    with pytest.raises(AppError, match="cannot be compared"):
        answer(df, filters=[{"column": "amount", "op": "greater_than", "value": "abc"}])


def test_limit_is_clamped_and_explained(df):
    checked = q.check_plan(df, plan(limit=10_000, group_by=["city"], sort="desc", metric="max", metric_column="amount",
                                    filters=[{"column": "email", "op": "is_not_missing", "value": ""}]))
    assert checked["limit"] == q.MAX_LIMIT
    assert q.explain(checked) == ["Keep rows where email is not empty", "Group by city",
                                  "Calculate: largest of amount", "Highest first, top 100"]


def test_empty_result(df):
    res = answer(df, group_by=["city"], filters=[{"column": "city", "op": "equals", "value": "Paris"}], description="X")
    assert res["rows"] == [] and res["answer"] == "X: no rows match."


def test_schema_follows_structured_output_rules():
    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node["required"]) == set(node["properties"])
            for bad in ("minLength", "maxLength", "minimum", "maximum"):
                assert bad not in node
            for v in node.values():
                check(v)
        elif isinstance(node, list):
            for v in node:
                check(v)
    check(q.PLAN_SCHEMA)


def test_works_on_converted_columns(df):
    from app.schemas.operations import CleanNumbers
    from app.services.operations import run_operation

    cleaned = run_operation(df, CleanNumbers(type="clean_numbers", columns=["amount"])).df
    res = answer(cleaned, metric="sum", metric_column="amount")
    assert res["rows"] == [[411.0]] and res["notes"] == []
    assert isinstance(pd.Series(res["rows"][0]).iloc[0], float)
