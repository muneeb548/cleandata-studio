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
    ],
    Field(discriminator="type"),
]

OPERATION_MODELS: dict[str, type[_Op]] = {
    m.model_fields["type"].annotation.__args__[0]: m  # type: ignore[union-attr]
    for m in (RemoveDuplicates, MissingValues, TrimWhitespace, StandardizeText, CleanColumnNames, ConvertType, RemoveEmpty, FindReplace)
}


class OperationRequest(BaseModel):
    """Body of POST /api/operations/preview and /api/operations/apply."""

    model_config = ConfigDict(extra="forbid")

    operation: Operation
    preview_token: Annotated[str, StringConstraints(max_length=128)] | None = Field(
        None,
        description="Token returned by the preview of the same operation. Required to apply operations that can remove data.",
    )
