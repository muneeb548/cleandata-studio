"""Country names from every country, and phone numbers read with each row's own country."""

import pandas as pd
import pytest

from app.schemas.operations import FlagRows, StandardizeCountry, StandardizePhone
from app.services import countries
from app.services import operations as ops


def values(series):
    return [None if pd.isna(v) else v for v in series.tolist()]


@pytest.mark.parametrize("text, code", [
    ("USA", "US"), ("U.S.A.", "US"), ("united states of america", "US"), ("America", "US"),
    ("UK", "GB"), ("England", "GB"), ("Great Britain", "GB"),
    ("Pakistan", "PK"), ("pak", "PK"), ("PK", "PK"),
    ("Deutschland", "DE"), ("México", "MX"), ("Türkiye", "TR"), ("Ivory Coast", "CI"),
    ("St Lucia", "LC"), ("Korea, South", "KR"), ("The Netherlands", "NL"), ("Holland", "NL"), ("UAE", "AE"),
    ("Namibia", "NA"),
])
def test_country_spellings(text, code):
    assert countries.country_code(text) == code


@pytest.mark.parametrize("text", ["N/A", "NA", "unknown", "", "  ", "-", "Amrika", None, 42])
def test_not_a_country(text):
    assert countries.country_code(text) is None


def test_every_country_has_a_name_and_aliases_point_to_known_codes():
    assert len(countries.COUNTRY_NAMES) >= 249
    assert set(countries.ALIASES) <= set(countries.COUNTRY_NAMES)
    for code, name in countries.COUNTRY_NAMES.items():
        assert countries.country_code(name) == code


# ----------------------------------------------------------------- standardize country names

def test_country_names_and_codes(frame):
    df = frame("country\nUSA\nu.k.\nPakistan\nAmrika\n\n")
    res = ops.run_operation(df, StandardizeCountry(type="standardize_country", columns=["country"]))
    assert values(res.df["country"])[:4] == ["United States", "United Kingdom", "Pakistan", "Amrika"]
    assert res.details["invalid_counts"] == {"country": 1} and res.warnings
    codes = ops.run_operation(df, StandardizeCountry(type="standardize_country", columns=["country"], output="code"))
    assert values(codes.df["country"])[:4] == ["US", "GB", "PK", "Amrika"]


# ----------------------------------------------------------------- phones with a country column

CUSTOMERS = (
    "phone,country\n"
    "(650) 253-0000,USA\n"
    "0300-1234567,Pakistan\n"
    "020 7031 3000,UK\n"
    "+44 20 7031 3000,Germany\n"   # a + number is read as written, whatever the country says
    "650.253.0000,Amrika\n"        # unknown country: the default (US) is used
    "not available,Ireland\n"
)


def test_phone_country_from_column(frame):
    op = StandardizePhone(type="standardize_phone", columns=["phone"], region="US", region_column="country",
                          format="e164")
    res = ops.run_operation(frame(CUSTOMERS), op)
    assert values(res.df["phone"]) == [
        "+16502530000", "+923001234567", "+442070313000", "+442070313000", "+16502530000", "not available",
    ]
    assert res.details["invalid_counts"] == {"phone": 1}
    assert any('"Amrika"' in w for w in res.warnings)


def test_phone_column_cannot_be_the_country_column(frame):
    from app.core.errors import AppError

    with pytest.raises(AppError):
        ops.run_operation(frame(CUSTOMERS), StandardizePhone(type="standardize_phone", columns=["phone", "country"],
                                                             region_column="country"))


def test_flag_phone_with_country_column(frame):
    op = FlagRows(type="flag_rows", rules=[{"column": "phone", "check": "invalid_phone", "region_column": "country"}])
    res = ops.run_operation(frame(CUSTOMERS), op)
    # Only "not available" is wrong; "650.253.0000" with an unknown country has no default here.
    assert values(res.df["needs_review"]) == [None, None, None, None, "Invalid phone in phone", "Invalid phone in phone"]
