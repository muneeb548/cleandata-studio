"""Combine files: add another file to the session, then append its rows or join its columns (like VLOOKUP)."""

import io

import openpyxl
import pandas as pd
import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.errors import AppError
from app.schemas import responses as R
from app.schemas.operations import CombineFiles, Operation
from app.services import combine, workspace
from app.services.operations import is_destructive
from app.services.sessions import SessionStore

from .conftest import preview_apply

CUSTOMERS = (
    "id,name,email\n"
    "1,Ali,ALI@x.com\n"
    "2,Sara,sara@x.com\n"
    "3,Omar,\n"
    "4,Zoya,zoya@x.com\n"
)
ORDERS = (
    "Email,amount,city\n"
    "ali@x.com ,100,Lahore\n"
    "sara@x.com,50,Karachi\n"
    "sara@x.com,70,Karachi\n"
    "new@x.com,5,Quetta\n"
)
MORE_CUSTOMERS = "name,id,phone\nBilal,5,0300\nHina,6,0301\n"

OP = TypeAdapter(Operation)


@pytest.fixture
def store():
    return SessionStore(ttl_seconds=600, max_sessions=10)


@pytest.fixture
def session(store):
    token = workspace.create_session(store, "customers.csv", CUSTOMERS.encode())["session_id"]
    return store.get(token)


def attach(store, session, text, name="orders.csv"):
    raw = text.encode() if isinstance(text, str) else text
    return workspace.attach_file(store, session, name, raw)["file"]["id"]


def join(file_id, **kw):
    params = {"type": "combine_files", "file_id": file_id, "mode": "join",
              "keys": [{"left": "email", "right": "Email"}], **kw}
    return CombineFiles(**params)


def values(series):
    return [None if pd.isna(v) else v for v in series.tolist()]


# ----------------------------------------------------------------- adding files

def test_attach_file_is_listed_and_validated(store, session):
    info = workspace.attach_file(store, session, "orders.csv", ORDERS.encode())
    R.AttachResponse.model_validate(info)
    assert info["file"]["rows"] == 4 and info["file"]["columns"] == ["Email", "amount", "city"]
    assert [f["name"] for f in info["session"]["files"]] == ["orders.csv"]
    preview = workspace.preview_file(session, info["file"]["id"])
    R.AttachedFilePreview.model_validate(preview)
    assert preview["preview"]["rows"][0] == ["ali@x.com ", "100", "Lahore"]
    # An added file never changes the working data or the history.
    assert len(session.current) == 4 and not session.history


def test_attach_rejects_bad_files(store, session):
    with pytest.raises(AppError) as err:
        workspace.attach_file(store, session, "empty.csv", b"")
    assert err.value.code == "empty_file"
    with pytest.raises(AppError):
        workspace.attach_file(store, session, "photo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 50)
    assert not session.files


def test_attach_limit_and_remove(store, session, monkeypatch):
    monkeypatch.setattr(workspace, "MAX_ATTACHED_FILES", 2)
    first = attach(store, session, ORDERS)
    attach(store, session, ORDERS, "orders2.csv")
    with pytest.raises(AppError) as err:
        attach(store, session, ORDERS, "orders3.csv")
    assert err.value.code == "too_many_files"
    info = workspace.remove_file(session, first)
    assert [f["name"] for f in info["files"]] == ["orders2.csv"]
    with pytest.raises(AppError) as err:
        workspace.remove_file(session, first)
    assert err.value.code == "file_not_found"


def test_attached_files_count_towards_memory_budget():
    store = SessionStore(ttl_seconds=600, max_sessions=10, max_total_bytes=10**9)
    s = store.get(workspace.create_session(store, "a.csv", CUSTOMERS.encode())["session_id"])
    before = s.memory_bytes
    attach(store, s, ORDERS)
    assert s.memory_bytes > before


def test_attach_never_removes_own_session_to_make_room():
    store = SessionStore(ttl_seconds=600, max_sessions=10, max_total_bytes=10**9, protect_seconds=0)
    old = workspace.create_session(store, "old.csv", CUSTOMERS.encode())["session_id"]
    s = store.get(workspace.create_session(store, "a.csv", CUSTOMERS.encode())["session_id"])
    big = ORDERS * 20
    from app.services.memory import frame_bytes

    from .conftest import load
    extra = frame_bytes(load(big).df)
    # Room for this session plus the new file only: the idle older session makes way, this one stays.
    store.max_total_bytes = s.memory_bytes + extra + 100
    attach(store, s, big)
    assert len(store) == 1 and s.files
    # No room at all: the file is refused and the session keeps its data.
    store.max_total_bytes = s.memory_bytes + 10
    with pytest.raises(AppError) as err:
        attach(store, s, big, "again.csv")
    assert err.value.code in ("file_too_large_for_server", "server_busy")
    assert len(s.files) == 1
    with pytest.raises(AppError):
        store.get(old)


def test_xlsx_file_can_be_added(store, session):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Email", "amount"])
    ws.append(["zoya@x.com", 42])
    buf = io.BytesIO()
    wb.save(buf)
    fid = attach(store, session, buf.getvalue(), "orders.xlsx")
    preview_apply(session, join(fid))
    assert values(session.current["amount"]) == [None, None, None, 42]


# ----------------------------------------------------------------- append

def test_append_matches_columns_by_name(store, session):
    fid = attach(store, session, MORE_CUSTOMERS, "more.csv")
    op = CombineFiles(type="combine_files", file_id=fid, mode="append")
    result = preview_apply(session, op)
    df = session.current
    assert len(df) == 6 and list(df.columns) == ["id", "name", "email", "phone"]
    assert values(df["name"]) == ["Ali", "Sara", "Omar", "Zoya", "Bilal", "Hina"]
    assert values(df["id"]) == ["1", "2", "3", "4", "5", "6"]
    assert values(df["phone"]) == [None, None, None, None, "0300", "0301"]
    assert result["rows_after"] == 6 and result["applied"]
    assert result["changes"]["added_rows"]["row_numbers"] == [5, 6]
    assert any('"phone"' in w for w in result["warnings"])
    assert any('"email"' in w for w in result["warnings"])
    # Existing rows keep their numbers, so Compare still lines up with the original.
    assert list(df.index) == [0, 1, 2, 3, 4, 5]
    assert workspace.compare(session)["rows_removed"] == 0


def test_append_source_column(store, session):
    fid = attach(store, session, MORE_CUSTOMERS, "more.csv")
    preview_apply(session, CombineFiles(type="combine_files", file_id=fid, mode="append", source_column="source"))
    assert values(session.current["source"]) == ["customers.csv"] * 4 + ["more.csv"] * 2


def test_append_source_column_must_be_new(store, session):
    fid = attach(store, session, MORE_CUSTOMERS, "more.csv")
    with pytest.raises(AppError) as err:
        workspace.preview_operation(session, CombineFiles(type="combine_files", file_id=fid, mode="append",
                                                          source_column="name"))
    assert err.value.code == "column_exists"


def test_append_blocks_files_without_common_columns(store, session):
    fid = attach(store, session, "a,b\n1,2\n", "other.csv")
    op = CombineFiles(type="combine_files", file_id=fid, mode="append")
    preview = workspace.preview_operation(session, op)
    assert preview["blocked"] and not preview["changed"]
    with pytest.raises(AppError) as err:
        workspace.apply_operation(session, op, preview["preview_token"])
    assert err.value.code == "operation_blocked"
    assert not session.history


def test_append_different_types_become_text(store, session):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["id", "name"])
    ws.append([5, "Bilal"])
    buf = io.BytesIO()
    wb.save(buf)
    fid = attach(store, session, buf.getvalue(), "more.xlsx")
    result = preview_apply(session, CombineFiles(type="combine_files", file_id=fid, mode="append"))
    assert values(session.current["id"]) == ["1", "2", "3", "4", "5"]
    assert result["details"]["retyped_columns"] == ["id"]


def test_append_twice_gives_unique_row_numbers(store, session):
    fid = attach(store, session, MORE_CUSTOMERS, "more.csv")
    op = CombineFiles(type="combine_files", file_id=fid, mode="append")
    preview_apply(session, op)
    preview_apply(session, op)
    assert len(session.current) == 8 and session.current.index.is_unique


# ----------------------------------------------------------------- join

def test_left_join_works_like_vlookup(store, session):
    fid = attach(store, session, ORDERS)
    result = preview_apply(session, join(fid))
    df = session.current
    assert len(df) == 4 and list(df.columns) == ["id", "name", "email", "amount", "city"]
    # Capitals and spaces are ignored by default; the first match is used for a repeated key.
    assert values(df["amount"]) == ["100", "50", None, None]
    assert values(df["city"]) == ["Lahore", "Karachi", None, None]
    assert result["details"]["matched_rows"] == 2 and result["details"]["unmatched_rows"] == 2
    assert result["cells_changed"] == 4
    assert any("first row" in w for w in result["warnings"])
    assert any("empty match value" in w for w in result["warnings"])
    assert list(df.index) == [0, 1, 2, 3]


def test_exact_keys_respect_capitals(store, session):
    fid = attach(store, session, ORDERS)
    preview_apply(session, join(fid, loose_keys=False))
    assert values(session.current["amount"]) == [None, "50", None, None]


def test_join_all_matches_repeats_rows(store, session):
    fid = attach(store, session, ORDERS)
    result = preview_apply(session, join(fid, duplicates="all"))
    df = session.current
    assert values(df["name"]) == ["Ali", "Sara", "Sara", "Omar", "Zoya"]
    assert values(df["amount"]) == ["100", "50", "70", None, None]
    assert df.index.is_unique and list(df.index[:2]) == [0, 1]
    assert result["details"]["rows_added"] == 1
    assert result["changes"]["added_rows"]["rows"][0][:2] == ["2", "Sara"]


def test_inner_join_removes_unmatched_rows_and_needs_preview(store, session):
    fid = attach(store, session, ORDERS)
    op = join(fid, how="inner")
    assert is_destructive(op)
    with pytest.raises(AppError) as err:
        workspace.apply_operation(session, op)
    assert err.value.code == "preview_required"
    preview = workspace.preview_operation(session, op)
    assert preview["rows_removed"] == 2
    assert preview["changes"]["removed_rows"]["row_numbers"] == [3, 4]
    workspace.apply_operation(session, op, preview["preview_token"])
    assert values(session.current["name"]) == ["Ali", "Sara"]


def test_outer_join_adds_unmatched_rows_of_other_file(store, session):
    fid = attach(store, session, ORDERS)
    preview_apply(session, join(fid, how="outer"))
    df = session.current
    assert values(df["email"]) == ["ALI@x.com", "sara@x.com", None, "zoya@x.com", "new@x.com"]
    assert values(df["city"])[-1] == "Quetta" and values(df["name"])[-1] is None


def test_join_selected_columns_and_name_clash(store, session):
    fid = attach(store, session, "Email,name,amount\nali@x.com,Ali Khan,1\n", "names.csv")
    result = preview_apply(session, join(fid, columns=["name"]))
    df = session.current
    assert list(df.columns) == ["id", "name", "email", "name_2"]
    assert values(df["name_2"]) == ["Ali Khan", None, None, None]
    assert result["details"]["renamed_columns"] == [{"before": "name", "after": "name_2"}]


def test_join_on_two_keys(store, session):
    fid = attach(store, session, "id,name,score\n1,Ali,9\n2,Wrong,8\n", "scores.csv")
    op = CombineFiles(type="combine_files", file_id=fid, mode="join",
                      keys=[{"left": "id", "right": "id"}, {"left": "name", "right": "name"}])
    preview_apply(session, op)
    assert values(session.current["score"]) == ["9", None, None, None]


def test_join_errors_are_clear(store, session):
    fid = attach(store, session, ORDERS)
    cases = [
        (join(fid, keys=[]), "no_keys"),
        (join(fid, keys=[{"left": "nope", "right": "Email"}]), "unknown_columns"),
        (join(fid, keys=[{"left": "email", "right": "nope"}]), "unknown_columns"),
        (join(fid, columns=["missing"]), "unknown_columns"),
        (join("unknown"), "file_not_found"),
    ]
    for op, code in cases:
        with pytest.raises(AppError) as err:
            workspace.preview_operation(session, op)
        assert err.value.code == code


def test_join_that_would_explode_is_blocked(store, session, monkeypatch):
    monkeypatch.setattr(combine, "MAX_RESULT_ROWS", 4)
    fid = attach(store, session, ORDERS)
    preview = workspace.preview_operation(session, join(fid, duplicates="all"))
    assert preview["blocked"] and "too large" in preview["blocked"]


def test_no_match_is_reported(store, session):
    fid = attach(store, session, "Email,amount\nnobody@x.com,1\n", "x.csv")
    preview = workspace.preview_operation(session, join(fid))
    assert any("No row matched" in w for w in preview["warnings"])


# ----------------------------------------------------------------- workflow safety

def test_preview_changes_nothing_and_undo_restores(store, session):
    fid = attach(store, session, ORDERS)
    original = session.current.copy()
    workspace.preview_operation(session, join(fid, how="outer", duplicates="all"))
    assert session.current.equals(original) and not session.history
    preview_apply(session, join(fid, how="outer", duplicates="all"))
    workspace.undo(session)
    assert session.current.equals(original)
    # The other file is never changed by the join.
    assert values(session.files[fid].df["Email"])[0] == "ali@x.com "


def test_removing_the_file_keeps_applied_result(store, session):
    fid = attach(store, session, ORDERS)
    preview_apply(session, join(fid))
    workspace.remove_file(session, fid)
    assert "amount" in session.current.columns
    workspace.undo(session)
    assert "amount" not in session.current.columns


def test_reset_keeps_added_files(store, session):
    fid = attach(store, session, ORDERS)
    preview_apply(session, join(fid))
    workspace.reset(session)
    assert fid in session.files and list(session.current.columns) == ["id", "name", "email"]


def test_compare_rows_and_export_after_combine(store, session):
    fid = attach(store, session, MORE_CUSTOMERS, "more.csv")
    preview_apply(session, CombineFiles(type="combine_files", file_id=fid, mode="append"))
    page = workspace.compare_rows(session)
    R.CompareRowsPage.model_validate(page)
    rows = workspace.get_rows(session)
    assert rows["row_numbers"] == [1, 2, 3, 4, 5, 6]
    data, _ = workspace.export_csv(session)
    assert data.decode().splitlines()[-1] == "6,Hina,,0301"
    R.Profile.model_validate(workspace.get_profile(session))


def test_recipe_leaves_out_combine_steps(store, session):
    fid = attach(store, session, ORDERS)
    preview_apply(session, join(fid))
    with pytest.raises(AppError) as err:
        workspace.recipe(session)
    assert err.value.code == "no_steps"
    workspace.apply_operation(session, OP.validate_python({"type": "standardize_text", "columns": ["name"], "case": "upper"}))
    recipe = workspace.recipe(session)
    R.Recipe.model_validate(recipe)
    assert [s["type"] for s in recipe["steps"]] == ["standardize_text"]
    assert len(recipe["left_out"]) == 1


def test_quick_clean_flow_accepts_combine(store, session):
    fid = attach(store, session, MORE_CUSTOMERS, "more.csv")
    ops = [OP.validate_python({"type": "combine_files", "file_id": fid, "mode": "append"}),
           OP.validate_python({"type": "trim_whitespace"})]
    preview = workspace.preview_quick_clean(session, ops)
    assert preview["rows_after"] == 6
    workspace.apply_quick_clean(session, ops, preview["preview_token"])
    assert len(session.current) == 6


def test_schema_rejects_bad_options():
    with pytest.raises(ValidationError):
        CombineFiles(type="combine_files", file_id="x", mode="zip")
    with pytest.raises(ValidationError):
        CombineFiles(type="combine_files", file_id="x", how="cross")
    with pytest.raises(ValidationError):
        CombineFiles(type="combine_files", file_id="x", unknown=1)
    assert CombineFiles(type="combine_files", file_id="x", source_column="  ").source_column is None


def test_session_info_lists_files(store, session):
    attach(store, session, ORDERS)
    info = workspace.session_info(session)
    R.SessionInfo.model_validate(info)
    assert info["files"][0]["columns"] == ["Email", "amount", "city"]


def test_ai_assistant_never_plans_combining(session):
    from app.services import ai

    assert "combine_files" not in ai.operation_guide() and "combine_files" not in ai.OPERATION_MODELS
    accepted, rejected = ai.validate_steps(session.current, [
        {"operation": "combine_files", "settings": '{"file_id": "x"}', "reason": ""}])
    assert not accepted and "Combine files" in rejected[0]["reason"]


# ------------------------------------------------- repeated keys on both sides (many-to-many)
# The case from a review: two sales rows and two reference rows with the same customer ID.
# A plain pandas merge turns them into four rows; the tool must never do that silently.
SALES = "order_id,customer_id,amount\n1,C001,100\n2,C001,50\n3,C002,70\n4,C003,30\n5,,20\n"
TIERS = "customer_id,tier\nC001,Gold\nC001,Silver\nC002,Bronze\nC002,Bronze\n"


@pytest.fixture
def sales(store):
    s = store.get(workspace.create_session(store, "sales.csv", SALES.encode())["session_id"])
    fid = workspace.attach_file(store, s, "tiers.csv", TIERS.encode())["file"]["id"]
    return s, fid


def tier_join(fid, **kw):
    return OP.validate_python({"type": "combine_files", "file_id": fid, "mode": "join",
                               "keys": [{"left": "customer_id", "right": "customer_id"}], **kw})


def test_many_to_many_first_match_keeps_row_count_and_names_the_conflict(sales):
    s, fid = sales
    result = preview_apply(s, tier_join(fid))
    df = s.current
    assert len(df) == 5  # not 2 x 2 = 4 rows for C001
    assert values(df["tier"]) == ["Gold", "Gold", "Bronze", None, None]
    d = result["details"]
    assert d["rows_before"] == 5 and d["rows_after"] == 5
    assert d["duplicate_keys_in_other"] == 2 and d["conflicting_duplicate_keys"] == 1
    assert d["duplicate_examples"][0]["value"] == "C001"  # the disagreeing one is listed first
    warning = next(w for w in result["warnings"] if "more than once" in w)
    assert "Gold, Silver" in warning and "may not be the right one" in warning


def test_many_to_many_every_match_reports_the_multiplication(sales):
    s, fid = sales
    result = preview_apply(s, tier_join(fid, duplicates="all"))
    df = s.current
    # C001: 2 sales x 2 tiers = 4 rows; C002: 1 sale x 2 tiers = 2 rows; C003 and the blank: 1 each.
    assert len(df) == 8
    assert values(df["order_id"]).count("1") == 2 and values(df["order_id"]).count("2") == 2
    assert result["details"]["rows_added"] == 3
    assert any("3 extra rows were added" in w and "5 → 8 rows" in w for w in result["warnings"])


def test_stop_option_blocks_repeated_keys_like_validate_many_to_one(sales):
    s, fid = sales
    preview = workspace.preview_operation(s, tier_join(fid, duplicates="stop"))
    assert preview["blocked"] and '"C001" (2 rows, different tier: Gold, Silver)' in preview["blocked"]
    assert '"C002" (2 rows)' in preview["blocked"]
    with pytest.raises(AppError):
        workspace.apply_operation(s, tier_join(fid, duplicates="stop"))
    assert len(s.current) == 5


def test_stop_option_passes_when_every_key_is_unique(store):
    s = store.get(workspace.create_session(store, "sales.csv", SALES.encode())["session_id"])
    fid = workspace.attach_file(store, s, "tiers.csv", b"customer_id,tier\nC001,Gold\nC002,Bronze\n")["file"]["id"]
    preview_apply(s, tier_join(fid, duplicates="stop"))
    assert values(s.current["tier"]) == ["Gold", "Gold", "Bronze", None, None]


def test_match_column_marks_each_row_like_indicator(sales):
    s, fid = sales
    result = preview_apply(s, tier_join(fid, match_column="match_status"))
    assert values(s.current["match_status"]) == ["matched", "matched", "matched", "no match", "empty key"]
    assert "match_status" in result["details"]["added_columns"]
    # Unmatched and empty keys are reported separately, not in one count.
    assert any(w.startswith("1 row of your data found no match") for w in result["warnings"])
    assert any(w.startswith("1 row of your data has an empty match value") for w in result["warnings"])
    assert "missing:match_status" not in {i["id"] for i in workspace.get_profile(s)["issues"]}


def test_match_column_with_outer_join_marks_rows_only_in_the_other_file(store):
    s = store.get(workspace.create_session(store, "sales.csv", SALES.encode())["session_id"])
    fid = workspace.attach_file(store, s, "tiers.csv", b"customer_id,tier\nC001,Gold\nC009,Silver\n")["file"]["id"]
    preview_apply(s, tier_join(fid, how="outer", match_column="match_status"))
    assert values(s.current["match_status"])[-1] == "only in tiers.csv"


def test_match_column_name_must_be_new(sales):
    s, fid = sales
    with pytest.raises(AppError) as err:
        workspace.preview_operation(s, tier_join(fid, match_column="amount"))
    assert err.value.code == "column_exists"
