"""Emails, amounts in any currency, and mapping many values at once."""

import pandas as pd
import pytest

from app.core.errors import AppError
from app.schemas.operations import CleanEmail, CleanNumbers, MapValues
from app.services import operations as ops


def values(series):
    return [None if pd.isna(v) else v for v in series.tolist()]


# ----------------------------------------------------------------- emails

EMAILS = 'email\n" EMMA.Watson@Yahoo.co.uk "\nmailto:ali@gmail.com\nali @ gmial.com\nali.khan@hotmail\n\n'


def test_clean_email_tidies_and_reports(frame):
    res = ops.run_operation(frame(EMAILS), CleanEmail(type="clean_email", columns=["email"]))
    assert values(res.df["email"])[:4] == ["emma.watson@yahoo.co.uk", "ali@gmail.com", "ali@gmial.com", "ali.khan@hotmail"]
    assert res.details["invalid_counts"] == {"email": 1}
    assert res.details["domain_fixes"] == 0


def test_clean_email_fixes_provider_typos_only_when_asked(frame):
    res = ops.run_operation(frame(EMAILS), CleanEmail(type="clean_email", columns=["email"], fix_domains=True))
    assert values(res.df["email"])[2] == "ali@gmail.com"
    assert res.details["domain_fixes"] == 1 and res.warnings


def test_clean_email_can_empty_invalid_values(frame):
    res = ops.run_operation(frame(EMAILS), CleanEmail(type="clean_email", columns=["email"], on_invalid="set_missing"))
    assert values(res.df["email"])[3] is None


# ----------------------------------------------------------------- numbers and currencies

@pytest.mark.parametrize("text, expected", [
    ("$1,250.00", 1250.0), ("Rs 1,250", 1250.0), ("1.234,56 €", 1234.56), ("(500)", -500.0), ("-75.5", -75.5),
    ("USD 2,000,000", 2000000.0), ("1 234,50", 1234.5), ("1'234.50", 1234.5), ("12,5", 12.5), ("£99.99", 99.99),
    ("1,25,000", 125000.0), ("Rs. 12,50,00,000", 125000000.0), ("PKR 150", 150.0), ("500-", -500.0),
])
def test_parse_amount(text, expected):
    assert ops.parse_amount(text)[0] == expected


@pytest.mark.parametrize("text", ["abc", "12 items", "1.2.3", "$", "1,2,3", "1,234.5.6"])
def test_parse_amount_rejects_non_numbers(text):
    assert ops.parse_amount(text)[0] is None


def test_european_decimal_comma_when_chosen():
    assert ops.parse_amount("1,250", ",")[0] == 1.25
    assert ops.parse_amount("1.234.567,8", ",")[0] == 1234567.8


def test_clean_numbers_blocks_on_invalid_by_default(frame):
    df = frame('amount\n"$1,250.00"\nabc\n')  # quoted: the comma belongs to the value
    res = ops.run_operation(df, CleanNumbers(type="clean_numbers", columns=["amount"]))
    assert res.blocked and res.details["invalid_counts"] == {"amount": 1}
    assert values(res.df["amount"]) == ["$1,250.00", "abc"]  # nothing changed


def test_clean_numbers_converts_and_warns(frame):
    df = frame('amount\n"$1,250.00"\n"€ 99,50"\n"1,250"\nabc\n\n')
    res = ops.run_operation(df, CleanNumbers(type="clean_numbers", columns=["amount"], on_error="set_missing"))
    assert values(res.df["amount"])[:4] == [1250.0, 99.5, 1250.0, None]
    assert str(res.df["amount"].dtype) == "Float64"
    assert any("mixes currencies" in w for w in res.warnings)
    assert any("two ways" in w for w in res.warnings)


# ----------------------------------------------------------------- value mapping

STATUS = "status,city\nPending,Isb\npend.,isb\n P ,Lahore\nPaid,ISB\n,Karachi\n"


def test_map_values_ignores_case_and_spaces(frame):
    op = MapValues(type="map_values", columns=["status"], mappings=[
        {"value": "pend.", "to": "Pending"}, {"value": "p", "to": "Pending"}, {"value": "nothing", "to": "x"},
    ])
    res = ops.run_operation(frame(STATUS), op)
    assert values(res.df["status"]) == ["Pending", "Pending", "Pending", "Paid", None]
    assert res.cells_changed == 2
    assert any('"nothing"' in w for w in res.warnings)


def test_map_values_exact_case(frame):
    op = MapValues(type="map_values", columns=["city"], ignore_case=False, mappings=[{"value": "Isb", "to": "Islamabad"}])
    res = ops.run_operation(frame(STATUS), op)
    assert values(res.df["city"]) == ["Islamabad", "isb", "Lahore", "ISB", "Karachi"]


def test_map_to_empty_makes_missing(frame):
    op = MapValues(type="map_values", columns=["city"], mappings=[{"value": "isb", "to": ""}])
    res = ops.run_operation(frame(STATUS), op)
    assert values(res.df["city"])[:2] == [None, None]


def test_conflicting_mappings_are_rejected(frame):
    op = MapValues(type="map_values", columns=["city"], mappings=[{"value": "isb", "to": "A"}, {"value": "ISB", "to": "B"}])
    with pytest.raises(AppError):
        ops.run_operation(frame(STATUS), op)


def test_column_values_endpoint(frame, fresh_store):
    from app.services import workspace

    session, _ = fresh_store.create(filename="s.csv", file_size=1, encoding="utf-8", delimiter=",",
                                    import_warnings=[], original=frame(STATUS))
    res = workspace.get_values(session, "city")
    assert res["distinct"] == 5 and not res["truncated"]
    assert {"value": "Lahore", "count": 1} in res["values"]
    with pytest.raises(AppError):
        workspace.get_values(session, "nope")
