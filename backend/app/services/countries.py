"""Country names and codes for every country (ISO 3166-1), with the spellings people actually type.

Used to read the country of a phone number from a column, and to write country
names in one consistent form ("USA", "U.S.A." and "america" -> "United States").
No external service and no extra dependency: the table lives here.
"""

from __future__ import annotations

import re
import unicodedata

# ISO alpha-2 code -> common English name. Includes every ISO 3166-1 country plus Kosovo (XK).
COUNTRY_NAMES: dict[str, str] = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan", "AG": "Antigua and Barbuda",
    "AI": "Anguilla", "AL": "Albania", "AM": "Armenia", "AO": "Angola", "AQ": "Antarctica", "AR": "Argentina",
    "AS": "American Samoa", "AT": "Austria", "AU": "Australia", "AW": "Aruba", "AX": "Åland Islands",
    "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina", "BB": "Barbados", "BD": "Bangladesh", "BE": "Belgium",
    "BF": "Burkina Faso", "BG": "Bulgaria", "BH": "Bahrain", "BI": "Burundi", "BJ": "Benin",
    "BL": "Saint Barthélemy", "BM": "Bermuda", "BN": "Brunei", "BO": "Bolivia", "BQ": "Caribbean Netherlands",
    "BR": "Brazil", "BS": "Bahamas", "BT": "Bhutan", "BV": "Bouvet Island", "BW": "Botswana", "BY": "Belarus",
    "BZ": "Belize", "CA": "Canada", "CC": "Cocos (Keeling) Islands", "CD": "Democratic Republic of the Congo",
    "CF": "Central African Republic", "CG": "Republic of the Congo", "CH": "Switzerland", "CI": "Côte d'Ivoire",
    "CK": "Cook Islands", "CL": "Chile", "CM": "Cameroon", "CN": "China", "CO": "Colombia", "CR": "Costa Rica",
    "CU": "Cuba", "CV": "Cape Verde", "CW": "Curaçao", "CX": "Christmas Island", "CY": "Cyprus", "CZ": "Czechia",
    "DE": "Germany", "DJ": "Djibouti", "DK": "Denmark", "DM": "Dominica", "DO": "Dominican Republic",
    "DZ": "Algeria", "EC": "Ecuador", "EE": "Estonia", "EG": "Egypt", "EH": "Western Sahara", "ER": "Eritrea",
    "ES": "Spain", "ET": "Ethiopia", "FI": "Finland", "FJ": "Fiji", "FK": "Falkland Islands", "FM": "Micronesia",
    "FO": "Faroe Islands", "FR": "France", "GA": "Gabon", "GB": "United Kingdom", "GD": "Grenada", "GE": "Georgia",
    "GF": "French Guiana", "GG": "Guernsey", "GH": "Ghana", "GI": "Gibraltar", "GL": "Greenland", "GM": "Gambia",
    "GN": "Guinea", "GP": "Guadeloupe", "GQ": "Equatorial Guinea", "GR": "Greece",
    "GS": "South Georgia and the South Sandwich Islands", "GT": "Guatemala", "GU": "Guam", "GW": "Guinea-Bissau",
    "GY": "Guyana", "HK": "Hong Kong", "HM": "Heard Island and McDonald Islands", "HN": "Honduras",
    "HR": "Croatia", "HT": "Haiti", "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland", "IL": "Israel",
    "IM": "Isle of Man", "IN": "India", "IO": "British Indian Ocean Territory", "IQ": "Iraq", "IR": "Iran",
    "IS": "Iceland", "IT": "Italy", "JE": "Jersey", "JM": "Jamaica", "JO": "Jordan", "JP": "Japan", "KE": "Kenya",
    "KG": "Kyrgyzstan", "KH": "Cambodia", "KI": "Kiribati", "KM": "Comoros", "KN": "Saint Kitts and Nevis",
    "KP": "North Korea", "KR": "South Korea", "KW": "Kuwait", "KY": "Cayman Islands", "KZ": "Kazakhstan",
    "LA": "Laos", "LB": "Lebanon", "LC": "Saint Lucia", "LI": "Liechtenstein", "LK": "Sri Lanka", "LR": "Liberia",
    "LS": "Lesotho", "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya", "MA": "Morocco",
    "MC": "Monaco", "MD": "Moldova", "ME": "Montenegro", "MF": "Saint Martin", "MG": "Madagascar",
    "MH": "Marshall Islands", "MK": "North Macedonia", "ML": "Mali", "MM": "Myanmar", "MN": "Mongolia",
    "MO": "Macao", "MP": "Northern Mariana Islands", "MQ": "Martinique", "MR": "Mauritania", "MS": "Montserrat",
    "MT": "Malta", "MU": "Mauritius", "MV": "Maldives", "MW": "Malawi", "MX": "Mexico", "MY": "Malaysia",
    "MZ": "Mozambique", "NA": "Namibia", "NC": "New Caledonia", "NE": "Niger", "NF": "Norfolk Island",
    "NG": "Nigeria", "NI": "Nicaragua", "NL": "Netherlands", "NO": "Norway", "NP": "Nepal", "NR": "Nauru",
    "NU": "Niue", "NZ": "New Zealand", "OM": "Oman", "PA": "Panama", "PE": "Peru", "PF": "French Polynesia",
    "PG": "Papua New Guinea", "PH": "Philippines", "PK": "Pakistan", "PL": "Poland",
    "PM": "Saint Pierre and Miquelon", "PN": "Pitcairn Islands", "PR": "Puerto Rico", "PS": "Palestine",
    "PT": "Portugal", "PW": "Palau", "PY": "Paraguay", "QA": "Qatar", "RE": "Réunion", "RO": "Romania",
    "RS": "Serbia", "RU": "Russia", "RW": "Rwanda", "SA": "Saudi Arabia", "SB": "Solomon Islands",
    "SC": "Seychelles", "SD": "Sudan", "SE": "Sweden", "SG": "Singapore", "SH": "Saint Helena", "SI": "Slovenia",
    "SJ": "Svalbard and Jan Mayen", "SK": "Slovakia", "SL": "Sierra Leone", "SM": "San Marino", "SN": "Senegal",
    "SO": "Somalia", "SR": "Suriname", "SS": "South Sudan", "ST": "São Tomé and Príncipe", "SV": "El Salvador",
    "SX": "Sint Maarten", "SY": "Syria", "SZ": "Eswatini", "TC": "Turks and Caicos Islands", "TD": "Chad",
    "TF": "French Southern Territories", "TG": "Togo", "TH": "Thailand", "TJ": "Tajikistan", "TK": "Tokelau",
    "TL": "Timor-Leste", "TM": "Turkmenistan", "TN": "Tunisia", "TO": "Tonga", "TR": "Turkey",
    "TT": "Trinidad and Tobago", "TV": "Tuvalu", "TW": "Taiwan", "TZ": "Tanzania", "UA": "Ukraine", "UG": "Uganda",
    "UM": "U.S. Minor Outlying Islands", "US": "United States", "UY": "Uruguay", "UZ": "Uzbekistan",
    "VA": "Vatican City", "VC": "Saint Vincent and the Grenadines", "VE": "Venezuela",
    "VG": "British Virgin Islands", "VI": "U.S. Virgin Islands", "VN": "Vietnam", "VU": "Vanuatu",
    "WF": "Wallis and Futuna", "WS": "Samoa", "XK": "Kosovo", "YE": "Yemen", "YT": "Mayotte",
    "ZA": "South Africa", "ZM": "Zambia", "ZW": "Zimbabwe",
}

# Other ways people write a country: official names, local names, three-letter codes, abbreviations.
ALIASES: dict[str, list[str]] = {
    "US": ["USA", "U.S.", "U.S.A.", "United States of America", "America", "Estados Unidos", "États-Unis"],
    "GB": ["UK", "U.K.", "GBR", "Great Britain", "Britain", "England", "Scotland", "Wales", "Northern Ireland",
           "United Kingdom of Great Britain and Northern Ireland"],
    "AE": ["UAE", "U.A.E.", "ARE", "Emirates"],
    "SA": ["KSA", "SAU", "Kingdom of Saudi Arabia", "Saudia"],
    "PK": ["PAK", "Pak", "Islamic Republic of Pakistan"],
    "IN": ["IND", "Bharat", "Republic of India"],
    "CN": ["CHN", "PRC", "People's Republic of China", "Mainland China"],
    "DE": ["DEU", "Deutschland", "Federal Republic of Germany"],
    "FR": ["FRA", "République française"],
    "ES": ["ESP", "España"],
    "IT": ["ITA", "Italia"],
    "NL": ["NLD", "Holland", "The Netherlands", "Nederland"],
    "BE": ["BEL", "Belgique", "België"],
    "CH": ["CHE", "Schweiz", "Suisse", "Svizzera"],
    "AT": ["AUT", "Österreich"],
    "SE": ["SWE", "Sverige"],
    "NO": ["NOR", "Norge"],
    "DK": ["DNK", "Danmark"],
    "FI": ["FIN", "Suomi"],
    "IE": ["IRL", "Éire", "Eire", "Republic of Ireland"],
    "PT": ["PRT"],
    "PL": ["POL", "Polska"],
    "GR": ["GRC", "Hellas"],
    "CZ": ["CZE", "Czech Republic"],
    "RO": ["ROU"],
    "HU": ["HUN", "Magyarország"],
    "HR": ["HRV", "Hrvatska"],
    "TR": ["TUR", "Türkiye", "Turkiye"],
    "RU": ["RUS", "Russian Federation"],
    "UA": ["UKR"],
    "CA": ["CAN"],
    "AU": ["AUS"],
    "NZ": ["NZL"],
    "MX": ["MEX", "México"],
    "BR": ["BRA", "Brasil"],
    "AR": ["ARG"],
    "CL": ["CHL"],
    "CO": ["COL"],
    "PE": ["PER"],
    "ZA": ["ZAF", "RSA"],
    "NG": ["NGA"],
    "KE": ["KEN"],
    "EG": ["EGY"],
    "QA": ["QAT"],
    "KW": ["KWT"],
    "OM": ["OMN"],
    "BH": ["BHR"],
    "BD": ["BGD", "Bangla Desh"],
    "LK": ["LKA", "Ceylon"],
    "NP": ["NPL"],
    "JP": ["JPN", "Nippon", "Nihon"],
    "KR": ["KOR", "Korea", "Republic of Korea", "Korea, South", "Korea, Republic of"],
    "KP": ["PRK", "DPRK", "Korea, North", "Democratic People's Republic of Korea"],
    "SG": ["SGP"],
    "MY": ["MYS"],
    "ID": ["IDN"],
    "PH": ["PHL", "The Philippines"],
    "TH": ["THA", "Siam"],
    "VN": ["VNM", "Viet Nam"],
    "HK": ["HKG", "Hong Kong SAR"],
    "MO": ["MAC", "Macau"],
    "TW": ["TWN", "Chinese Taipei"],
    "IL": ["ISR"],
    "IR": ["IRN", "Iran, Islamic Republic of", "Persia"],
    "SY": ["Syrian Arab Republic"],
    "LA": ["Lao", "Lao PDR", "Lao People's Democratic Republic"],
    "BO": ["Bolivia, Plurinational State of"],
    "VE": ["Venezuela, Bolivarian Republic of"],
    "TZ": ["Tanzania, United Republic of"],
    "MD": ["Republic of Moldova", "Moldova, Republic of"],
    "MK": ["Macedonia", "FYROM"],
    "MM": ["Burma"],
    "SZ": ["Swaziland"],
    "CV": ["Cabo Verde"],
    "TL": ["East Timor"],
    "VA": ["Holy See", "Vatican"],
    "PS": ["Palestinian Territories", "State of Palestine"],
    "CI": ["Ivory Coast", "Cote d'Ivoire"],
    "CD": ["DRC", "DR Congo", "Congo-Kinshasa", "Democratic Republic of Congo", "Congo, Democratic Republic of the"],
    "CG": ["Congo", "Congo-Brazzaville", "Republic of Congo"],
    "BN": ["Brunei Darussalam"],
    "FM": ["Federated States of Micronesia"],
    "BS": ["The Bahamas"],
    "GM": ["The Gambia"],
    "CY": ["CYP"],
    "IS": ["ISL"],
    "LU": ["LUX"],
    "MT": ["MLT"],
    "EE": ["EST"],
    "LV": ["LVA"],
    "LT": ["LTU"],
    "SK": ["SVK"],
    "SI": ["SVN"],
    "BG": ["BGR"],
    "RS": ["SRB"],
    "JO": ["JOR"],
    "LB": ["LBN"],
    "IQ": ["IRQ"],
    "AF": ["AFG"],
    "MA": ["MAR"],
    "DZ": ["DZA"],
    "TN": ["TUN"],
    "GH": ["GHA"],
    "ET": ["ETH"],
}


def normalize(value: str) -> str:
    """Comparable form of a country name: no accents, case, punctuation or leading "the"."""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    text = re.sub(r"^the ", "", text)
    text = re.sub(r"\bst\b", "saint", text)  # "St Lucia" == "Saint Lucia"
    # "U.S.A." became "u s a": join single letters so it matches "usa".
    if re.fullmatch(r"(?:[a-z] )+[a-z]", text):
        text = text.replace(" ", "")
    return text


def _build_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for code, name in COUNTRY_NAMES.items():
        lookup[normalize(name)] = code
        lookup[code.lower()] = code
    for code, names in ALIASES.items():
        for alias in names:
            lookup.setdefault(normalize(alias), code)
    return lookup


_LOOKUP = _build_lookup()


# "N/A" would otherwise read as NA (Namibia): placeholders are never a country.
_PLACEHOLDERS = {"na", "n a", "none", "null", "nil", "unknown", "not available", "not applicable", "missing", "nan"}


def country_code(value: object) -> str | None:
    """ISO alpha-2 code for a country written in any common way, or None when it is not recognised."""
    if not isinstance(value, str):
        return None
    raw = re.sub(r"[^a-z]+", " ", value.lower()).strip()
    if raw in _PLACEHOLDERS:
        return None
    key = normalize(value)
    return _LOOKUP.get(key) if key else None


def country_name(code: str) -> str:
    return COUNTRY_NAMES[code]
