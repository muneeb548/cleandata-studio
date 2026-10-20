"""Save the applied steps as a recipe and repeat them on next week's file."""

import json

import pytest
from pydantic import TypeAdapter

from app.core.errors import AppError
from app.schemas.operations import Operation, QuickCleanRequest
from app.schemas.responses import Recipe
from app.services import workspace

from .conftest import preview_apply

OP = TypeAdapter(Operation)

WEEK_1 = "customer,city,status\n Ali ,lahore,paid\nSara,LAHORE,Paid\nSara,LAHORE,Paid\n"
WEEK_2 = "customer,city,status\nOmar ,lahore ,PAID\nZoya,Lahore,paid\nZoya,Lahore,paid\nBilal,karachi,Pending\n"


def make(store, frame, text, name="week.csv"):
    s, _ = store.create(filename=name, file_size=1, encoding="utf-8", delimiter=",", import_warnings=[], original=frame(text))
    return s


def test_recipe_repeats_the_cleaning_on_a_new_file(frame, fresh_store):
    week1 = make(fresh_store, frame, WEEK_1, "sales_week1.csv")
    for params in (
        {"type": "remove_duplicates", "keep": "first"},
        {"type": "trim_whitespace", "columns": []},
        {"type": "standardize_text", "columns": ["city", "status"], "case": "title"},
    ):
        preview_apply(week1, OP.validate_python(params))
    recipe = workspace.recipe(week1)
    Recipe.model_validate(recipe)
    assert recipe["name"] == "sales_week1 cleanup" and len(recipe["steps"]) == 3

    # The recipe survives a round trip through a .json file and the API's request model.
    saved = json.loads(json.dumps(recipe))
    ops = QuickCleanRequest(operations=saved["steps"]).operations

    week2 = make(fresh_store, frame, WEEK_2)
    preview = workspace.preview_quick_clean(week2, ops)
    result = workspace.apply_quick_clean(week2, ops, preview["preview_token"])
    assert result["applied"] == 3
    df = week2.current
    assert len(df) == 3
    assert df["customer"].tolist() == ["Omar", "Zoya", "Bilal"]
    assert df["city"].tolist() == ["Lahore", "Lahore", "Karachi"]
    assert df["status"].tolist() == ["Paid", "Paid", "Pending"]


def test_recipe_with_a_missing_column_is_refused(frame, fresh_store):
    ops = QuickCleanRequest(operations=[{"type": "standardize_text", "columns": ["region"], "case": "title"}]).operations
    with pytest.raises(AppError) as exc:
        workspace.preview_quick_clean(make(fresh_store, frame, WEEK_2), ops)
    assert exc.value.code == "unknown_columns"


def test_no_recipe_before_any_step(frame, fresh_store):
    with pytest.raises(AppError) as exc:
        workspace.recipe(make(fresh_store, frame, WEEK_1))
    assert exc.value.code == "no_steps"
