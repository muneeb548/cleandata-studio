import dataclasses
import io
import time

import pandas as pd
import pytest

from app.core.errors import AppError
from app.services import workspace as ws
from app.services.operations import ConvertType, MissingValues, RemoveDuplicates, StandardizeText, TrimWhitespace
from app.services.sessions import SessionStore

from .conftest import preview_apply  # noqa: F401
from .conftest import MESSY_CSV


def upload(store, text=MESSY_CSV, name="people.csv"):
    info = ws.create_session(store, name, text.encode("utf-8"))
    return store.get(info["session_id"]), info


def test_upload_returns_file_details(fresh_store):
    _, info = upload(fresh_store)
    assert info["file"]["name"] == "people.csv"
    assert info["current_shape"] == {"rows": 6, "columns": 5}
    assert info["can_undo"] is False


def test_apply_undo_reset(fresh_store):
    s, _ = upload(fresh_store)
    original = s.original.copy()

    r1 = preview_apply(s, RemoveDuplicates(type="remove_duplicates"))
    assert r1["applied"] and len(s.current) == 5
    r2 = preview_apply(s, TrimWhitespace(type="trim_whitespace"))
    assert r2["applied"] and s.current.loc[0, "Name "] == "Ali"
    assert len(s.history) == 2

    ws.undo(s)
    assert len(s.history) == 1
    assert s.current.loc[0, "Name "] == "  Ali "  # trim undone, dedupe kept
    assert len(s.current) == 5

    ws.reset(s)
    assert s.history == []
    pd.testing.assert_frame_equal(s.current, original)
    pd.testing.assert_frame_equal(s.original, original)  # original never overwritten


def test_undo_with_empty_history(fresh_store):
    s, _ = upload(fresh_store)
    with pytest.raises(AppError) as exc:
        ws.undo(s)
    assert exc.value.code == "cannot_undo"


def test_preview_does_not_change_data(fresh_store):
    s, _ = upload(fresh_store)
    p = ws.preview_operation(s, RemoveDuplicates(type="remove_duplicates"))
    assert p["rows_removed"] == 1
    assert p["destructive"] is True
    assert p["changes"]["removed_rows"]["row_numbers"] == [3]
    assert len(s.current) == 6 and s.history == []


def test_preview_cell_samples(fresh_store):
    s, _ = upload(fresh_store)
    p = ws.preview_operation(s, StandardizeText(type="standardize_text", columns=["City"], case="title"))
    assert p["cells_changed"] == 3
    assert {"row": 2, "column": "City", "before": "lahore", "after": "Lahore"} in p["changes"]["cell_samples"]


def test_no_change_is_not_recorded(fresh_store):
    s, _ = upload(fresh_store, "a\n1\n2\n")
    r = preview_apply(s, RemoveDuplicates(type="remove_duplicates"))
    assert r["applied"] is False
    assert s.history == []


def test_blocked_conversion_cannot_be_applied(fresh_store):
    s, _ = upload(fresh_store)
    with pytest.raises(AppError) as exc:
        preview_apply(s, ConvertType(type="convert_type", columns=["Joined"], target="datetime"))
    assert exc.value.code == "operation_blocked"
    assert s.history == []


def test_compare_counts(fresh_store):
    s, _ = upload(fresh_store)
    preview_apply(s, RemoveDuplicates(type="remove_duplicates"))
    preview_apply(s, MissingValues(type="missing_values", strategy="fill_constant", columns=["Salary"], value="0"))
    c = ws.compare(s)
    assert c["original"]["rows"] == 6 and c["current"]["rows"] == 5
    assert c["rows_removed"] == 1
    assert c["original"]["duplicate_rows"] == 1 and c["current"]["duplicate_rows"] == 0
    assert c["original"]["missing_cells"] == 3 and c["current"]["missing_cells"] == 1
    assert c["cells_modified"] == 1
    assert len(c["operations"]) == 2


def test_compare_counts_placeholders_as_missing_before_and_after(fresh_store):
    """Turning "N/A" into a real empty cell must not look like the data got worse."""
    from app.schemas.operations import MapValues

    text = "name,status\nAli,active\nSara,N/A\nZoe,N/A\nBob,active\n"
    s, _ = upload(fresh_store, text, "q.csv")
    preview_apply(s, MapValues(type="map_values", columns=["status"], mappings=[{"value": "N/A", "to": ""}]))
    c = ws.compare(s)
    assert c["original"]["missing_cells"] == 0 and c["current"]["missing_cells"] == 2  # plain counts
    q = c["quality"]
    assert q["original"]["missing_cells"] == 2 and q["current"]["missing_cells"] == 2
    assert q["original"]["completeness"] == q["current"]["completeness"] == 75.0
    assert q["original"]["columns_with_missing"] == q["current"]["columns_with_missing"] == 1
    assert q["current"]["problems"] <= q["original"]["problems"]


def test_csv_export_round_trip(fresh_store):
    text = 'id,comment,city\n1,"Hello, ""world""",لاہور\n2,"two\nlines",\n'
    s, _ = upload(fresh_store, text, "notes.csv")
    content, name = ws.export_csv(s)
    assert name == "notes_cleaned.csv"
    back = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    assert back.loc[0, "comment"] == 'Hello, "world"'
    assert back.loc[1, "comment"] == "two\nlines"
    assert back.loc[0, "city"] == "لاہور"
    assert list(back.columns) == ["id", "comment", "city"]


def test_export_uses_current_not_original(fresh_store):
    s, _ = upload(fresh_store)
    preview_apply(s, RemoveDuplicates(type="remove_duplicates"))
    content, _ = ws.export_csv(s)
    assert content.decode("utf-8").count("\n") == 6  # header + 5 rows


def test_export_preserves_original_text_exactly(fresh_store):
    text = "code,price\n007,3.10\n010,1e3\n"
    s, _ = upload(fresh_store, text)
    content, _ = ws.export_csv(s)
    assert content.decode("utf-8") == text


def test_export_bom_and_empty_dataset(fresh_store):
    s, _ = upload(fresh_store, "a,b\n")
    content, _ = ws.export_csv(s, "my file", bom=True)
    assert content.startswith(b"\xef\xbb\xbf")
    assert content.decode("utf-8-sig") == "a,b\n"


@pytest.mark.parametrize("requested,expected", [
    ("report", "report.csv"),
    ("report.CSV", "report.csv"),
    ("../../evil", "evil.csv"),
    ("a<b>:c", "a_b__c.csv"),
    ("", "people_cleaned.csv"),
    ("...", "cleaned_data.csv"),
])
def test_safe_output_name(requested, expected):
    assert ws.safe_output_name(requested, "people.csv") == expected


def test_session_isolation(fresh_store):
    a, ia = upload(fresh_store, "x\n1\n", "a.csv")
    b, ib = upload(fresh_store, "y\n2\n", "b.csv")
    ta, tb = ia["session_id"], ib["session_id"]
    assert a.id != b.id and ta != tb
    preview_apply(a, MissingValues(type="missing_values", strategy="fill_constant", columns=["x"], value="9"))
    preview_apply(a, StandardizeText(type="standardize_text", columns=["x"], case="upper"))
    assert list(fresh_store.get(tb).current.columns) == ["y"]
    assert fresh_store.get(tb).history == []
    assert fresh_store.get(ta) is a and fresh_store.get(tb) is b
    for bad in ["guessed-id", a.id, f"{a.id}.{'A' * 43}", f"{b.id}.{ta.split('.')[1]}", ta + "x", "../../etc/passwd"]:
        with pytest.raises(AppError) as exc:
            fresh_store.get(bad)
        assert exc.value.status == 404
    with pytest.raises(AppError) as exc:
        fresh_store.get(None)
    assert exc.value.status == 401


def test_token_secret_is_not_stored(fresh_store):
    s, info = upload(fresh_store)
    secret = info["session_id"].split(".")[1]
    assert secret not in repr(vars(s)) and secret.encode() not in s.secret_hash


def test_delete_requires_valid_token(fresh_store):
    s, info = upload(fresh_store)
    assert fresh_store.delete(s.id) is False  # public id alone is not enough
    assert fresh_store.delete(info["session_id"]) is True
    with pytest.raises(AppError):
        fresh_store.get(info["session_id"])


def test_session_expiry():
    store = SessionStore(ttl_seconds=1, max_sessions=5)
    s, info = upload(store)
    s.last_access = time.time() - 5
    with pytest.raises(AppError) as exc:
        store.get(info["session_id"])
    assert exc.value.code == "session_expired"
    assert len(store) == 0  # expired session is removed, not just hidden


def test_cleanup_removes_expired_sessions():
    store = SessionStore(ttl_seconds=60, max_sessions=5)
    s, _ = upload(store)
    s.last_access -= 120
    assert store.cleanup() == 1 and len(store) == 0


def test_session_limit_evicts_oldest():
    store = SessionStore(ttl_seconds=600, max_sessions=2)
    first, info = upload(store)
    first.last_access -= 100
    upload(store)
    upload(store)
    assert len(store) == 2
    with pytest.raises(AppError):
        store.get(info["session_id"])


def test_history_snapshot_pruning(fresh_store, monkeypatch):
    monkeypatch.setattr(ws, "settings", dataclasses.replace(ws.settings, max_history_snapshots=2))
    s, _ = upload(fresh_store, "c\na\nb\n")
    for case in ["upper", "lower", "upper", "lower"]:
        entry = preview_apply(s, StandardizeText(type="standardize_text", columns=["c"], case=case))
        assert entry["applied"]
    assert len(s.history) == 4  # every step stays in the activity log
    assert [h.df is not None for h in s.history] == [False, False, True, True]
    assert s.can_undo
    ws.undo(s)
    assert not s.can_undo  # the step before is no longer stored
    assert s.current.loc[0, "c"] == "A"


def test_profile_and_rows_endpoints(fresh_store):
    s, _ = upload(fresh_store)
    prof = ws.get_profile(s, "original")
    assert prof["stats"]["rows"] == 6
    page = ws.get_rows(s, "current", page=1, page_size=2, search="lahore")
    assert page["total_rows"] == 4
    assert len(page["rows"]) == 2
    sorted_page = ws.get_rows(s, sort_by="Salary", sort_dir="desc")
    assert sorted_page["rows"][0][3] == "1000000"  # numeric sort, not text sort
    assert sorted_page["rows"][-1][3] is None  # missing values last
    with pytest.raises(AppError):
        ws.get_rows(s, "something-else")


def test_page_size_is_capped(fresh_store):
    s, _ = upload(fresh_store)
    assert ws.get_rows(s, page_size=10_000)["page_size"] == ws.settings.max_page_size


def test_compare_rows_aligns_and_highlights(fresh_store):
    s, _ = upload(fresh_store)
    preview_apply(s, RemoveDuplicates(type="remove_duplicates"))
    preview_apply(s, StandardizeText(type="standardize_text", columns=["City"], case="title"))
    res = ws.compare_rows(s, page=1, page_size=10)
    assert res["total_rows"] == 6
    by_row = {r["row"]: r for r in res["rows"]}
    assert by_row[3]["current"] is None  # the duplicate that was removed
    city = res["current_columns"].index("City")
    assert by_row[2]["original"][1] == "lahore" and by_row[2]["current"][city] == "Lahore"
    assert by_row[2]["changed"][city] is True
    assert by_row[1]["changed"] == [False] * 5  # "Lahore" was already title case


def test_compare_rows_changes_only_and_renames(fresh_store):
    s, _ = upload(fresh_store)
    preview_apply(s, RemoveDuplicates(type="remove_duplicates"))
    only = ws.compare_rows(s, changes_only=True)
    assert [r["row"] for r in only["rows"]] == [3]
    ws.reset(s)
    from app.services.operations import CleanColumnNames
    preview_apply(s, CleanColumnNames(type="clean_column_names", lowercase=True))
    res = ws.compare_rows(s)
    assert "name" in res["renamed_or_new"]
    assert not any(any(r["changed"]) for r in res["rows"])  # renamed columns are not compared
    assert ws.compare_rows(s, changes_only=True)["total_rows"] == 0
