"""Saved sessions (SAVE_SESSIONS=true): work survives a server restart and never expires with TTL 0."""

import time

import pandas as pd
import pytest
from pydantic import TypeAdapter

from app.core.errors import AppError
from app.schemas import responses as R
from app.schemas.operations import Operation
from app.services import workspace
from app.services.sessions import SessionStore

from .conftest import MESSY_CSV, preview_apply

OP = TypeAdapter(Operation)
ORDERS = "Name,city2\nAli,Lahore\nSara,Karachi\n"


def make_store(tmp_path, ttl=0):
    return SessionStore(ttl_seconds=ttl, max_sessions=10, saved_dir=str(tmp_path / "saved"))


def restart(tmp_path, ttl=0):
    """A new store on the same folder = the server was restarted (memory is empty)."""
    return make_store(tmp_path, ttl)


def values(series):
    return [None if pd.isna(v) else v for v in series.tolist()]


def test_work_survives_a_restart(tmp_path):
    store = make_store(tmp_path)
    token = workspace.create_session(store, "people.csv", MESSY_CSV.encode())["session_id"]
    s = store.get(token)
    fid = workspace.attach_file(store, s, "orders.csv", ORDERS.encode())["file"]["id"]
    preview_apply(s, OP.validate_python({"type": "trim_whitespace"}))
    preview_apply(s, OP.validate_python({"type": "remove_duplicates"}))
    preview_apply(s, OP.validate_python({"type": "combine_files", "file_id": fid, "mode": "join",
                                         "keys": [{"left": "Name ", "right": "Name"}]}))
    before = s.current.copy()
    info_before = workspace.session_info(s)

    store2 = restart(tmp_path)
    s2 = store2.get(token)
    assert s2.current.equals(before)
    assert [h.type for h in s2.history] == ["trim_whitespace", "remove_duplicates", "combine_files"]
    info = workspace.session_info(s2)
    R.SessionInfo.model_validate(info)
    assert info["saved"] is True and info["files"][0]["name"] == "orders.csv"
    assert info["log"] == info_before["log"]
    # Undo still works after the restart, step by step.
    workspace.undo(s2)
    assert "city2" not in s2.current.columns and len(s2.current) == 5


def test_undo_and_reset_are_saved_too(tmp_path):
    store = make_store(tmp_path)
    token = workspace.create_session(store, "people.csv", MESSY_CSV.encode())["session_id"]
    s = store.get(token)
    preview_apply(s, OP.validate_python({"type": "trim_whitespace"}))
    preview_apply(s, OP.validate_python({"type": "remove_duplicates"}))
    workspace.undo(s)
    assert [h.type for h in restart(tmp_path).get(token).history] == ["trim_whitespace"]
    workspace.reset(s)
    s3 = restart(tmp_path).get(token)
    assert s3.history == [] and s3.current.equals(s.original)


def test_removed_file_still_rebuilds_its_step(tmp_path):
    store = make_store(tmp_path)
    token = workspace.create_session(store, "people.csv", MESSY_CSV.encode())["session_id"]
    s = store.get(token)
    fid = workspace.attach_file(store, s, "more.csv", MESSY_CSV.encode())["file"]["id"]
    unused = workspace.attach_file(store, s, "unused.csv", ORDERS.encode())["file"]["id"]
    preview_apply(s, OP.validate_python({"type": "combine_files", "file_id": fid, "mode": "append"}))
    workspace.remove_file(s, fid)
    workspace.remove_file(s, unused)
    assert workspace.session_info(s)["files"] == []
    s2 = restart(tmp_path).get(token)
    assert len(s2.current) == 12 and workspace.session_info(s2)["files"] == []
    assert not (tmp_path / "saved" / s.id / "files" / f"{unused}.pkl").exists()


def test_never_expires_with_ttl_zero(tmp_path):
    store = make_store(tmp_path, ttl=0)
    token = workspace.create_session(store, "people.csv", MESSY_CSV.encode())["session_id"]
    s = store.get(token)
    s.last_access = time.time() - 10 * 365 * 24 * 3600  # ten years later
    assert store.cleanup() == 0
    assert store.get(token) is s


def test_expiry_also_deletes_the_saved_copy(tmp_path):
    store = make_store(tmp_path, ttl=60)
    token = workspace.create_session(store, "people.csv", MESSY_CSV.encode())["session_id"]
    sid = token.split(".")[0]
    s = store.get(token)
    s.last_access = time.time() - 3600
    store.disk.touch(s)
    store2 = restart(tmp_path, ttl=60)
    with pytest.raises(AppError):
        store2.get(token)
    assert not store2.disk.exists(sid)


def test_wrong_secret_cannot_open_a_saved_session(tmp_path):
    store = make_store(tmp_path)
    token = workspace.create_session(store, "people.csv", MESSY_CSV.encode())["session_id"]
    sid = token.split(".")[0]
    store2 = restart(tmp_path)
    with pytest.raises(AppError):
        store2.get(f"{sid}.{'A' * 43}")
    assert store2.delete(f"{sid}.{'A' * 43}") is False and store2.disk.exists(sid)
    assert store2.get(token).id == sid


def test_delete_removes_it_from_disk(tmp_path):
    store = make_store(tmp_path)
    token = workspace.create_session(store, "people.csv", MESSY_CSV.encode())["session_id"]
    sid = token.split(".")[0]
    assert store.delete(token) is True
    assert not store.disk.exists(sid)
    with pytest.raises(AppError):
        restart(tmp_path).get(token)


def test_delete_after_restart_without_loading(tmp_path):
    store = make_store(tmp_path)
    token = workspace.create_session(store, "people.csv", MESSY_CSV.encode())["session_id"]
    store2 = restart(tmp_path)
    assert store2.delete(token) is True and not store2.disk.exists(token.split(".")[0])


def test_session_reloads_after_leaving_memory(tmp_path):
    store = SessionStore(ttl_seconds=0, max_sessions=1, saved_dir=str(tmp_path / "saved"))
    first = workspace.create_session(store, "a.csv", MESSY_CSV.encode())["session_id"]
    preview_apply(store.get(first), OP.validate_python({"type": "trim_whitespace"}))
    workspace.create_session(store, "b.csv", MESSY_CSV.encode())  # pushes "a" out of memory
    assert len(store) == 1
    assert [h.type for h in store.get(first).history] == ["trim_whitespace"]


def test_damaged_step_is_dropped_not_fatal(tmp_path):
    import json

    store = make_store(tmp_path)
    token = workspace.create_session(store, "people.csv", MESSY_CSV.encode())["session_id"]
    s = store.get(token)
    preview_apply(s, OP.validate_python({"type": "trim_whitespace"}))
    preview_apply(s, OP.validate_python({"type": "remove_duplicates"}))
    meta_path = tmp_path / "saved" / s.id / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["history"][1]["params"] = {"type": "standardize_text", "columns": ["no such column"]}
    meta_path.write_text(json.dumps(meta))
    s2 = restart(tmp_path).get(token)
    assert [h.type for h in s2.history] == ["trim_whitespace"]
    assert "could not be repeated" in s2.log[-1].summary


def test_without_saving_nothing_is_written(tmp_path):
    store = SessionStore(ttl_seconds=600, max_sessions=10)
    token = workspace.create_session(store, "people.csv", MESSY_CSV.encode())["session_id"]
    assert store.disk is None and store.get(token).saver is None
    assert workspace.session_info(store.get(token))["saved"] is False
