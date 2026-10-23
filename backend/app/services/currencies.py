"""Which currency an amount is in, for "Convert all to one currency" in Clean numbers.

A value's own mark decides when it is clear (USD, £, €, ₹). Marks used by several
currencies ($, Rs, ¥) and plain numbers are settled by the row's country when a country
column is given (Pakistan -> PKR, Canada -> CAD), otherwise by the chosen default currency.
Exchange rates are never guessed: the user types them, because they change every day.
"""

from __future__ import annotations

# Marks that name exactly one currency.
CLEAR_MARKS = {
    "US$": "USD", "C$": "CAD", "A$": "AUD", "NZ$": "NZD", "R$": "BRL", "HK$": "HKD", "S$": "SGD",
    "€": "EUR", "£": "GBP", "₹": "INR", "₩": "KRW", "₽": "RUB", "₺": "TRY", "₦": "NGN", "₱": "PHP",
    "฿": "THB", "₫": "VND", "₪": "ILS", "RMB": "CNY",
}
# Marks shared by several currencies: (currencies they can mean, used when nothing else says which).
SHARED_MARKS = {
    "$": ({"USD", "CAD", "AUD", "NZD", "SGD", "HKD", "MXN", "ARS", "CLP", "COP"}, "USD"),
    "Rs": ({"PKR", "INR", "LKR", "NPR"}, None),
    "₨": ({"PKR", "INR", "LKR", "NPR"}, None),
    "¥": ({"JPY", "CNY"}, "JPY"),
}

# Country (ISO 3166 alpha-2) -> currency (ISO 4217).
_EURO = "AT BE HR CY EE FI FR DE GR IE IT LV LT LU MT NL PT SK SI ES AD MC SM VA ME XK".split()
COUNTRY_CURRENCY = {c: "EUR" for c in _EURO}
COUNTRY_CURRENCY.update({
    "US": "USD", "GB": "GBP", "PK": "PKR", "IN": "INR", "AE": "AED", "SA": "SAR", "QA": "QAR", "KW": "KWD",
    "OM": "OMR", "BH": "BHD", "CA": "CAD", "AU": "AUD", "NZ": "NZD", "JP": "JPY", "CN": "CNY", "CH": "CHF",
    "SE": "SEK", "NO": "NOK", "DK": "DKK", "PL": "PLN", "CZ": "CZK", "HU": "HUF", "RO": "RON", "BG": "BGN",
    "TR": "TRY", "ZA": "ZAR", "NG": "NGN", "KE": "KES", "EG": "EGP", "MA": "MAD", "BD": "BDT", "LK": "LKR",
    "NP": "NPR", "AF": "AFN", "IR": "IRR", "IQ": "IQD", "JO": "JOD", "LB": "LBP", "IL": "ILS", "MY": "MYR",
    "SG": "SGD", "HK": "HKD", "PH": "PHP", "TH": "THB", "ID": "IDR", "VN": "VND", "KR": "KRW", "TW": "TWD",
    "BR": "BRL", "MX": "MXN", "AR": "ARS", "CL": "CLP", "CO": "COP", "PE": "PEN", "RU": "RUB", "UA": "UAH",
    "GH": "GHS", "ET": "ETB", "TZ": "TZS", "UG": "UGX", "PR": "USD", "EC": "USD", "SV": "USD", "PA": "USD",
    "IS": "ISK", "RS": "RSD", "BA": "BAM", "MK": "MKD", "AL": "ALL", "GE": "GEL", "AM": "AMD", "AZ": "AZN",
    "KZ": "KZT", "UZ": "UZS", "MM": "MMK", "KH": "KHR", "MV": "MVR", "DZ": "DZD", "TN": "TND", "LY": "LYD",
    "SD": "SDG",
})

# Codes the user can choose (target and default): every currency above.
KNOWN = sorted(set(COUNTRY_CURRENCY.values()) | set(CLEAR_MARKS.values())
               | {c for codes, _ in SHARED_MARKS.values() for c in codes})


def mark_currency(mark: str | None) -> tuple[str | None, set[str] | None]:
    """(currency, None) for a clear mark; (fallback or None, possible currencies) for a shared one;
    (None, None) when there is no mark."""
    if not mark:
        return None, None
    if mark in CLEAR_MARKS:
        return CLEAR_MARKS[mark], None
    if mark in SHARED_MARKS:
        options, fallback = SHARED_MARKS[mark]
        return fallback, options
    code = mark.upper()
    if len(code) == 3 and code.isalpha():
        return code, None  # written as a code: USD, PKR, GBP...
    return None, None


def resolve(mark: str | None, country_currency: str | None, default: str | None) -> str | None:
    """The currency of one value: its own clear mark, else the row's country (when it fits the
    mark), else the default. None when it cannot be known."""
    clear, options = mark_currency(mark)
    if mark and options is None:
        return clear
    if options is not None:  # $, Rs, ¥
        if country_currency in options:
            return country_currency
        if default in options:
            return default
        return clear  # the usual meaning ($ -> USD, ¥ -> JPY) or None for Rs
    return country_currency or default
