"""Pydantic models for cleaning-operation parameters.

Every request that changes data is validated here before any pandas code runs:
unknown fields are rejected (`extra="forbid"`), strings and lists have size
limits, and enum-like options only accept known values. Rules that depend on
the data itself (for example "this column must be numeric") are checked in
`app.services.operations`, which returns friendlier messages.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

MAX_COLUMNS_PER_OPERATION = 5000
ColumnName = Annotated[str, StringConstraints(max_length=1000)]
ColumnList = Annotated[list[ColumnName], Field(max_length=MAX_COLUMNS_PER_OPERATION)]

# strftime/strptime directives pandas accepts; anything else is almost certainly a typo.
_DATE_DIRECTIVES = set("aAwdbBmyYHIpMSfzjUWcxX%GuV")


class _Op(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class RemoveDuplicates(_Op):
    """Delete rows that are exact copies of another row."""

    type: Literal["remove_duplicates"]
    keep: Literal["first", "last"] = Field("first", description="Which copy of each duplicate group to keep.")


class MissingValues(_Op):
    """Fill or remove missing (empty) cells in the selected columns."""

    type: Literal["missing_values"]
    strategy: Literal["drop_rows", "drop_columns", "fill_mean", "fill_median", "fill_constant"]
    columns: ColumnList = Field(default_factory=list, description="Columns to inspect. Required.")
    value: Annotated[str, StringConstraints(max_length=10_000)] | None = Field(
        None, description="Fill value; required when strategy is fill_constant."
    )


class TrimWhitespace(_Op):
    """Remove leading and trailing spaces from text cells."""

    type: Literal["trim_whitespace"]
    columns: ColumnList = Field(default_factory=list, description="Empty list = all text columns.")


class StandardizeText(_Op):
    """Convert text to lowercase, UPPERCASE or Title Case."""

    type: Literal["standardize_text"]
    columns: ColumnList = Field(default_factory=list)
    case: Literal["lower", "upper", "title"] = "lower"


class CleanColumnNames(_Op):
    """Trim column names, replace spaces with underscores and keep every name unique."""

    type: Literal["clean_column_names"]
    replace_spaces: bool = True
    lowercase: bool = False


class ConvertType(_Op):
    """Convert columns to integer, decimal, text or datetime."""

    type: Literal["convert_type"]
    columns: ColumnList = Field(default_factory=list)
    target: Literal["integer", "float", "string", "datetime"]
    on_error: Literal["set_missing", "abort"] = Field(
        "abort", description="abort: refuse to apply if any value cannot be converted; set_missing: convert and report them."
    )
    date_format: Annotated[str, StringConstraints(max_length=50)] | None = Field(
        None, description="Optional strptime format such as %d/%m/%Y."
    )
    dayfirst: bool = False

    @field_validator("date_format")
    @classmethod
    def _check_format(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        if "%" not in value:
            raise ValueError("a date format must contain at least one % directive, e.g. %Y-%m-%d")
        for directive in re.findall(r"%(.)", value):
            if directive not in _DATE_DIRECTIVES:
                raise ValueError(f"unsupported date directive %{directive}")
        return value


class RemoveEmpty(_Op):
    """Remove rows and/or columns in which every cell is missing."""

    type: Literal["remove_empty"]
    target: Literal["rows", "columns", "both"] = "both"


class FindReplace(_Op):
    """Replace a value (or text inside values) in the selected text columns."""

    type: Literal["find_replace"]
    columns: ColumnList = Field(default_factory=list)
    find: Annotated[str, StringConstraints(max_length=1000)]
    replace: Annotated[str, StringConstraints(max_length=1000)] = ""
    match: Literal["exact", "contains"] = "exact"
    case_sensitive: bool = True


NewColumnName = Annotated[str, StringConstraints(min_length=1, max_length=200)]


def _clean_new_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("a new column name cannot be empty")
    return name


class SplitColumn(_Op):
    """Split one text column into several new columns, e.g. a full name into first and last name."""

    type: Literal["split_column"]
    column: ColumnName
    separator: Annotated[str, StringConstraints(min_length=1, max_length=20)] = Field(
        " ", description='Text between the parts. " " (a space) splits on any run of spaces.'
    )
    names: Annotated[list[NewColumnName], Field(min_length=2, max_length=10)] = Field(
        description="Names of the new columns, in order. The last one receives any remaining text."
    )
    split_from: Literal["start", "end"] = Field(
        "start", description='start: "Ali Raza Khan" -> "Ali" + "Raza Khan"; end: -> "Ali Raza" + "Khan".'
    )
    keep_original: bool = True

    @field_validator("names")
    @classmethod
    def _check_names(cls, value: list[str]) -> list[str]:
        names = [_clean_new_name(v) for v in value]
        if len(set(names)) != len(names):
            raise ValueError("the new column names must be different from each other")
        return names


class MergeColumns(_Op):
    """Join several columns into one new column, e.g. first and last name into a full name."""

    type: Literal["merge_columns"]
    columns: Annotated[list[ColumnName], Field(min_length=2, max_length=20)]
    separator: Annotated[str, StringConstraints(max_length=20)] = " "
    new_name: NewColumnName
    keep_originals: bool = True

    @field_validator("new_name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        return _clean_new_name(value)


RegionCode = Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{2}$")]


def _upper_region(value: str | None) -> str | None:
    return value.upper() if value else value


class StandardizePhone(_Op):
    """Write phone numbers from any country in one consistent format and report the ones that are not valid."""

    type: Literal["standardize_phone"]
    columns: ColumnList = Field(default_factory=list)
    region: RegionCode = Field(
        "US", description="Two-letter country code (US, GB, DE, PK...) used for numbers written without a + country code."
    )
    region_column: ColumnName | None = Field(
        None,
        description="Column that says which country each row is from (e.g. 'country'). Rows whose country is "
                    "empty or not recognised use `region`.",
    )
    format: Literal["national", "international", "e164"] = Field(
        "international",
        description="national: (415) 555-2671, international: +1 415-555-2671, e164: +14155552671.",
    )
    on_invalid: Literal["keep", "set_missing"] = Field(
        "keep", description="keep: leave values that are not valid numbers unchanged (they are reported)."
    )

    @field_validator("region")
    @classmethod
    def _check_region(cls, value: str | None) -> str | None:
        return _upper_region(value)


class StandardizeCountry(_Op):
    """Write country names in one form ("USA", "U.S.A.", "america" -> "United States") or as ISO codes."""

    type: Literal["standardize_country"]
    columns: ColumnList = Field(default_factory=list)
    output: Literal["name", "code"] = Field("name", description='name: "United States"; code: "US" (ISO 3166-1).')


class CleanEmail(_Op):
    """Tidy email addresses (spaces, capitals, "mailto:") and report the ones that are not valid."""

    type: Literal["clean_email"]
    columns: ColumnList = Field(default_factory=list)
    lowercase: bool = Field(True, description="ALI@Gmail.com -> ali@gmail.com.")
    fix_domains: bool = Field(
        False, description="Fix common typos of big email providers: gmial.com -> gmail.com, hotmail.con -> hotmail.com."
    )
    on_invalid: Literal["keep", "set_missing"] = "keep"


class CurrencyRate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    rate: float = Field(gt=0, le=1_000_000_000, description="How much one unit is worth in the target currency.")


class CleanNumbers(_Op):
    """Turn amounts written as text ("$1,250.00", "Rs 1,250", "1.234,56 €", "(500)") into real numbers."""

    type: Literal["clean_numbers"]
    columns: ColumnList = Field(default_factory=list)
    decimal: Literal["auto", ".", ","] = Field(
        "auto", description='auto: decide per value; ".": 1,234.56 (US/UK); ",": 1.234,56 (most of Europe).'
    )
    on_error: Literal["abort", "set_missing"] = Field(
        "abort", description="abort: refuse to apply if a value is not a number; set_missing: convert and report them."
    )
    convert_to: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = Field(
        None, description="Convert every amount to this currency (ISO code such as USD). Needs a rate for each "
                          "other currency found."
    )
    rates: Annotated[list[CurrencyRate], Field(max_length=60)] = Field(
        default_factory=list, description="Exchange rates typed by the user: 1 <currency> = <rate> <convert_to>."
    )
    country_column: ColumnName | None = Field(
        None, description="Column with each row's country; decides the currency of plain numbers and of marks "
                          "shared by several currencies ($, Rs, ¥)."
    )
    default_currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = Field(
        None, description="Currency of amounts that have no mark (and no country)."
    )

    @field_validator("rates")
    @classmethod
    def _unique_rates(cls, value: list["CurrencyRate"]) -> list["CurrencyRate"]:
        codes = [r.currency for r in value]
        if len(set(codes)) != len(codes):
            raise ValueError("each currency can have only one rate")
        return value


class ValueMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Annotated[str, StringConstraints(max_length=1000)] = Field(description="The value as it appears now.")
    to: Annotated[str, StringConstraints(max_length=1000)] = Field(description="What it should become. Empty = missing.")


class MapValues(_Op):
    """Replace many values at once from a table, e.g. "pend.", "P" and "pending" -> "Pending"."""

    type: Literal["map_values"]
    columns: ColumnList = Field(default_factory=list)
    mappings: Annotated[list[ValueMapping], Field(min_length=1, max_length=1000)]
    ignore_case: bool = Field(True, description="Also match the values written in other capitals and with outer spaces.")


class NearDuplicates(_Op):
    """Find rows that are the same person or thing written slightly differently ("Ali Khan" / "ali  khan.")."""

    type: Literal["near_duplicates"]
    columns: Annotated[list[ColumnName], Field(min_length=1, max_length=20)] = Field(
        description="Columns that identify a record, e.g. name and email."
    )
    match: Literal["normalized", "similar"] = Field(
        "normalized",
        description="normalized: equal after ignoring capitals, accents, spaces and punctuation; "
                    "similar: also small spelling differences (about 90% alike).",
    )
    action: Literal["flag", "remove"] = Field(
        "flag", description="flag: add a column with a group number; remove: keep the first row of each group."
    )
    column_name: NewColumnName = "duplicate_group"

    @field_validator("column_name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        return _clean_new_name(value)


class FlagRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: ColumnName
    check: Literal["missing", "invalid_email", "invalid_phone", "not_number", "not_date", "duplicate_value", "out_of_range"]
    region: RegionCode | None = Field(
        None, description="invalid_phone only: country for numbers written without a + country code."
    )
    region_column: ColumnName | None = Field(
        None, description="invalid_phone only: column that says which country each row is from."
    )
    min: Annotated[str, StringConstraints(max_length=50)] | None = Field(
        None, description="out_of_range only: smallest allowed value, a number (0) or a date (2024-01-01)."
    )
    max: Annotated[str, StringConstraints(max_length=50)] | None = Field(
        None, description="out_of_range only: largest allowed value, a number (120) or a date."
    )

    @field_validator("region")
    @classmethod
    def _check_region(cls, value: str | None) -> str | None:
        return _upper_region(value)


class FlagRows(_Op):
    """Add a review column that says why each row needs attention. No data is changed or removed."""

    type: Literal["flag_rows"]
    rules: Annotated[list[FlagRule], Field(min_length=1, max_length=50)]
    column_name: NewColumnName = "needs_review"

    @field_validator("column_name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        return _clean_new_name(value)


class ColumnRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: ColumnName
    to: NewColumnName

    @field_validator("to")
    @classmethod
    def _check_to(cls, value: str) -> str:
        return _clean_new_name(value)


class OrganizeColumns(_Op):
    """Rename, remove and reorder columns, for example to match the columns a CRM or another system expects."""

    type: Literal["organize_columns"]
    rename: Annotated[list[ColumnRename], Field(max_length=MAX_COLUMNS_PER_OPERATION)] = Field(
        default_factory=list, description="New names for some columns.")
    drop: ColumnList = Field(default_factory=list, description="Columns to remove.")
    order: ColumnList = Field(
        default_factory=list,
        description="Columns to put first, in this order (current names); the other columns follow in their current order.")


class SortKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: ColumnName
    direction: Literal["asc", "desc"] = "asc"


class SortRows(_Op):
    """Sort the rows (numbers as numbers, dates as dates, text A-Z ignoring capitals). The download keeps this order."""

    type: Literal["sort_rows"]
    by: Annotated[list[SortKey], Field(min_length=1, max_length=5)]
    missing: Literal["last", "first"] = Field("last", description="Where rows with an empty value go.")


class JoinKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: ColumnName = Field(description="Column in the working data.")
    right: ColumnName = Field(description="Column in the other file with the same values.")


class CombineFiles(_Op):
    """Combine the working data with another file added to this session.

    append: add the other file's rows below (columns are matched by name).
    join: add the other file's columns to matching rows, like Excel VLOOKUP (rows matched by key columns).
    """

    type: Literal["combine_files"]
    file_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    mode: Literal["append", "join"] = "append"
    # append
    source_column: NewColumnName | None = Field(
        None, description="append: optional new column that records which file each row came from."
    )
    # join
    keys: Annotated[list[JoinKey], Field(max_length=5)] = Field(
        default_factory=list, description="join: columns whose values must be equal for two rows to match."
    )
    how: Literal["left", "inner", "outer"] = Field(
        "left", description="join: left keeps every row of the working data; inner keeps only matched rows; "
                            "outer also adds rows of the other file that matched nothing."
    )
    loose_keys: bool = Field(True, description="join: ignore capitals and extra spaces when comparing keys.")
    duplicates: Literal["first", "all"] = Field(
        "first", description="join: when a key appears several times in the other file, use the first match "
                             "(like VLOOKUP) or every match (rows are repeated)."
    )
    columns: ColumnList = Field(
        default_factory=list, description="join: columns to bring from the other file. Empty = all except the keys."
    )
    suffix: Annotated[str, StringConstraints(min_length=1, max_length=50)] = Field(
        "_2", description="join: added to a brought column whose name is already used."
    )

    @field_validator("source_column")
    @classmethod
    def _check_source(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        return _clean_new_name(value)


Operation = Annotated[
    Union[
        RemoveDuplicates,
        MissingValues,
        TrimWhitespace,
        StandardizeText,
        CleanColumnNames,
        ConvertType,
        RemoveEmpty,
        FindReplace,
        SplitColumn,
        MergeColumns,
        StandardizePhone,
        StandardizeCountry,
        CleanEmail,
        CleanNumbers,
        MapValues,
        NearDuplicates,
        FlagRows,
        OrganizeColumns,
        SortRows,
        CombineFiles,
    ],
    Field(discriminator="type"),
]

OPERATION_MODELS: dict[str, type[_Op]] = {
    m.model_fields["type"].annotation.__args__[0]: m  # type: ignore[union-attr]
    for m in (RemoveDuplicates, MissingValues, TrimWhitespace, StandardizeText, CleanColumnNames, ConvertType, RemoveEmpty,
              FindReplace, SplitColumn, MergeColumns, StandardizePhone, StandardizeCountry, CleanEmail, CleanNumbers, MapValues, NearDuplicates, FlagRows,
              OrganizeColumns, SortRows, CombineFiles)
}


class OperationRequest(BaseModel):
    """Body of POST /api/operations/preview and /api/operations/apply."""

    model_config = ConfigDict(extra="forbid")

    operation: Operation
    preview_token: Annotated[str, StringConstraints(max_length=128)] | None = Field(
        None,
        description="Token returned by the preview of the same operation. Required to apply operations that can remove data.",
    )


class QuickCleanRequest(BaseModel):
    """Body of POST /api/quick-clean/preview and /api/quick-clean/apply."""

    model_config = ConfigDict(extra="forbid")

    operations: Annotated[list[Operation], Field(min_length=1, max_length=100)]
    preview_token: Annotated[str, StringConstraints(max_length=128)] | None = None
