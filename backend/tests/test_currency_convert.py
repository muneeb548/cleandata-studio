"""Clean numbers → Convert all to one currency."""

import pandas as pd
import pytest
from pydantic import ValidationError

from app.schemas.operations import CleanNumbers
from app.services.currencies import resolve
from app.services.operations import run_operation

CSV = (
    "name,country,spent\n"
    "Ali,Pakistan,\"Rs 28,000\"\n"
    "Sara,Pakistan,14000\n"
    "John,USA,$100.50\n"
    "Emma,UK,£200\n"
    "Liam,Canada,$50\n"
    "Omar,,\"PKR 2,800\"\n"
    "Zoya,UAE,USD 10\n"
)
RATES = [{"currency": "PKR", "rate": 1 / 280}, {"currency": "GBP", "rate": 1.25}, {"currency": "CAD", "rate": 0.75}]


def op(**kw):
    return CleanNumbers(type="clean_numbers", columns=["spent"], decimal=".", **kw)


def values(series):
    return [None if pd.isna(v) else float(v) for v in series.tolist()]


def test_marks_and_countries_decide_the_currency():
    assert resolve("£", "PKR", None) == "GBP"          # a clear mark always wins
    assert resolve("$", "CAD", None) == "CAD"          # $ in Canada
    assert resolve("$", None, None) == "USD"           # $ alone
    assert resolve("Rs", "PKR", None) == "PKR"
    assert resolve("Rs", None, None) is None           # rupee of which country?
    assert resolve("Rs", None, "INR") == "INR"
    assert resolve(None, "PKR", "USD") == "PKR"        # plain number: the row's country
    assert resolve(None, None, "USD") == "USD"
    assert resolve("PKR", None, None) == "PKR"


def test_convert_with_country_column(frame):
    df = frame(CSV)
    res = run_operation(df, op(convert_to="USD", rates=RATES, country_column="country"))
    assert not res.blocked
    assert values(res.df["spent"]) == [100.0, 50.0, 100.5, 250.0, 37.5, 10.0, 10.0]
    assert res.details["converted_counts"] == {"PKR": 3, "USD": 2, "GBP": 1, "CAD": 1}
    assert res.summary == "Converted 7 amounts to USD."
    assert any("1 PKR = 0.003571 USD" in w for w in res.warnings)


def test_missing_rate_blocks_and_changes_nothing(frame):
    df = frame(CSV)
    res = run_operation(df, op(convert_to="USD", rates=RATES[:1], country_column="country"))
    assert res.blocked and "CAD, GBP" in res.blocked
    assert res.df["spent"].equals(df["spent"])


def test_plain_number_without_country_needs_a_default(frame):
    df = frame("spent\n$5\n100\n")
    blocked = run_operation(df, op(convert_to="USD"))
    assert blocked.blocked and "no currency" in blocked.blocked
    ok = run_operation(df, op(convert_to="USD", default_currency="PKR", rates=[{"currency": "PKR", "rate": 0.01}]))
    assert values(ok.df["spent"]) == [5.0, 1.0]
    lenient = run_operation(df, op(convert_to="USD", on_error="set_missing"))
    assert values(lenient.df["spent"]) == [5.0, None]
    assert any("no currency" in w for w in lenient.warnings)


def test_preview_without_converting_counts_currencies(frame):
    res = run_operation(frame(CSV), op(country_column="country"))
    assert res.details["currency_counts"] == {"PKR": 3, "USD": 2, "GBP": 1, "CAD": 1}
    assert values(res.df["spent"])[0] == 28000.0  # not converted
    assert any("Convert all to one currency" in w for w in res.warnings)


def test_country_column_cannot_be_converted(frame):
    from app.core.errors import AppError

    with pytest.raises(AppError):
        run_operation(frame(CSV), CleanNumbers(type="clean_numbers", columns=["spent", "country"],
                                                country_column="country"))


def test_schema_checks():
    with pytest.raises(ValidationError):
        op(convert_to="usd")
    with pytest.raises(ValidationError):
        op(convert_to="USD", rates=[{"currency": "PKR", "rate": 0}])
    with pytest.raises(ValidationError):
        op(convert_to="USD", rates=[{"currency": "PKR", "rate": 1}, {"currency": "PKR", "rate": 2}])
