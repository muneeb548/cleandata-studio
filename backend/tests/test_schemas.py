"""The documented response models must match what the services really return."""

import pytest
from pydantic import ValidationError

from app.schemas import responses as R
from app.schemas.operations import ConvertType, FindReplace, OperationRequest
from app.services import workspace as ws
from app.services.operations import ConvertType as ConvertTypeAlias, RemoveDuplicates, StandardizeText

from .conftest import MESSY_CSV, preview_apply


@pytest.fixture
def session(fresh_store):
    info = ws.create_session(fresh_store, "people.csv", MESSY_CSV.encode())
    return fresh_store.get(info["session_id"]), info


def test_upload_and_session_match_schema(session):
    s, info = session
    R.UploadResponse.model_validate(info)
    R.SessionInfo.model_validate(ws.session_info(s))


def test_profile_rows_and_outliers_match_schema(session):
    s, _ = session
    R.Profile.model_validate(ws.get_profile(s))
    R.Profile.model_validate(ws.get_profile(s, "original", light=True))
    R.RowsPage.model_validate(ws.get_rows(s, page=1, page_size=3, sort_by="Salary"))
    R.OutlierReport.model_validate(ws.get_outliers(s, "Salary"))


def test_operation_flow_matches_schema(session):
    s, _ = session
    preview = ws.preview_operation(s, RemoveDuplicates(type="remove_duplicates"))
    R.OperationPreview.model_validate(preview)
    R.ApplyResponse.model_validate(ws.apply_operation(s, RemoveDuplicates(type="remove_duplicates"), preview["preview_token"]))
    R.ApplyResponse.model_validate(preview_apply(s, StandardizeText(type="standardize_text", columns=["City"], case="upper")))
    R.HistoryResponse.model_validate(ws.history(s))
    R.CompareResponse.model_validate(ws.compare(s))
    R.CompareRowsPage.model_validate(ws.compare_rows(s))
    R.UndoResponse.model_validate(ws.undo(s))
    R.ResetResponse.model_validate(ws.reset(s))
    R.HistoryResponse.model_validate(ws.history(s))


def test_blocked_preview_matches_schema(session):
    s, _ = session
    p = ws.preview_operation(s, ConvertType(type="convert_type", columns=["Joined"], target="datetime"))
    assert p["blocked"]
    R.OperationPreview.model_validate(p)


def test_catalog_matches_schema_and_lists_every_operation():
    catalog = ws.operations_catalog()
    for item in catalog:
        R.OperationInfo.model_validate(item)
    assert {c["type"] for c in catalog} == {
        "remove_duplicates", "missing_values", "trim_whitespace", "standardize_text",
        "clean_column_names", "convert_type", "remove_empty", "find_replace",
        "split_column", "merge_columns", "standardize_phone", "standardize_country", "flag_rows",
    }
    mv = next(c for c in catalog if c["type"] == "missing_values")
    assert mv["may_remove_data"] and "strategy" in mv["required"]
    assert set(mv["parameters"]["strategy"]["enum"]) == {"drop_rows", "drop_columns", "fill_mean", "fill_median", "fill_constant"}


def test_models_are_the_same_objects():
    assert ConvertType is ConvertTypeAlias


@pytest.mark.parametrize("body", [
    {"operation": {"type": "explode"}},
    {"operation": {"type": "trim_whitespace", "columns": [], "unexpected": True}},
    {"operation": {"type": "remove_duplicates", "keep": "middle"}},
    {"operation": {"type": "convert_type", "columns": ["a"], "target": "datetime", "date_format": "%Q"}},
    {"operation": {"type": "convert_type", "columns": ["a"], "target": "datetime", "date_format": "dd/mm/yyyy"}},
    {"operation": {"type": "find_replace", "columns": ["a"], "find": "x" * 1001}},
    {"operation": {"type": "standardize_text", "columns": ["c"] * 5001}},
    {"operation": {"type": "trim_whitespace", "columns": "City"}},
    {"operation": {"type": "remove_duplicates"}, "surprise": 1},
])
def test_invalid_operation_bodies_are_rejected(body):
    with pytest.raises(ValidationError):
        OperationRequest.model_validate(body)


def test_valid_date_format_is_kept():
    op = ConvertType(type="convert_type", columns=["d"], target="datetime", date_format="%d/%m/%Y %H:%M")
    assert op.date_format == "%d/%m/%Y %H:%M"
    assert ConvertType(type="convert_type", columns=["d"], target="datetime", date_format="  ").date_format is None


def test_find_replace_defaults():
    op = FindReplace(type="find_replace", columns=["a"], find="N/A")
    assert op.replace == "" and op.match == "exact" and op.case_sensitive is True
