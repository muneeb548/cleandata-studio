"""Upload size limits and Undo/Reset behaviour (backend)."""

import dataclasses

import pandas as pd
import pytest

from app.core.config import Settings, settings
from app.core.errors import AppError
from app.services import workspace as ws
from app.services.operations import FindReplace, RemoveDuplicates, StandardizeText, TrimWhitespace

from .conftest import preview_apply  # noqa: F401
from .conftest import MESSY_CSV


def test_default_upload_limit_is_100_mb(monkeypatch):
    monkeypatch.delenv("MAX_UPLOAD_MB", raising=False)
    assert Settings().max_upload_mb == 100
    assert Settings().max_upload_bytes == 100 * 1024 * 1024
    assert settings.max_upload_bytes == settings.max_upload_mb * 1024 * 1024


def test_limit_is_configurable_by_environment(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "250")
    assert Settings().max_upload_mb == 250
    assert Settings().max_upload_bytes == 250 * 1024 * 1024


@pytest.fixture
def small_limit(monkeypatch):
    """Simulate the limit with 1 MB so the boundary can be tested quickly."""
    monkeypatch.setattr(ws, "settings", dataclasses.replace(ws.settings, max_upload_mb=1))
    return 1024 * 1024


def _csv_of_size(size: int) -> bytes:
    header = b"value\n"
    line = b"abcdefghi\n"  # 10 bytes
    body = line * ((size - len(header)) // len(line))
    data = header + body
    return data + b"x" * (size - len(data) - 1) + b"\n" if len(data) < size else data


@pytest.mark.parametrize("delta", [-1, 0])
def test_files_below_and_at_the_limit_are_accepted(fresh_store, small_limit, delta):
    raw = _csv_of_size(small_limit + delta)
    assert len(raw) == small_limit + delta
    info = ws.create_session(fresh_store, "edge.csv", raw)
    assert info["file"]["size"] == len(raw)


def test_file_above_the_limit_is_rejected(fresh_store, small_limit):
    raw = _csv_of_size(small_limit + 1)
    with pytest.raises(AppError) as exc:
        ws.create_session(fresh_store, "big.csv", raw)
    assert exc.value.code == "file_too_large" and exc.value.status == 413
    assert "1 MB" in exc.value.message
    assert len(fresh_store) == 0  # nothing half-imported


def test_upload_temp_files_are_deleted(fresh_store, tmp_path, monkeypatch):
    monkeypatch.setattr(ws.tempfile, "tempdir", str(tmp_path))
    ws.create_session(fresh_store, "a.csv", b"a\n1\n")
    with pytest.raises(AppError):
        ws.create_session(fresh_store, "b.csv", b"")
    assert list(tmp_path.iterdir()) == []


# ----------------------------------------------------------------- undo / reset

def _session(store, text=MESSY_CSV):
    info = ws.create_session(store, "people.csv", text.encode())
    return store.get(info["session_id"])


def test_undo_restores_exact_previous_state(fresh_store):
    s = _session(fresh_store)
    preview_apply(s, RemoveDuplicates(type="remove_duplicates"))
    after_first = s.current.copy()
    preview_apply(s, TrimWhitespace(type="trim_whitespace"))
    res = ws.undo(s)
    pd.testing.assert_frame_equal(s.current, after_first)
    assert res["undone"]["type"] == "trim_whitespace"
    assert res["session"]["current_shape"]["rows"] == 5
    assert res["session"]["can_undo"] is True
    ws.undo(s)
    pd.testing.assert_frame_equal(s.current, s.original)
    assert ws.session_info(s)["can_undo"] is False


def test_second_undo_without_history_fails_cleanly(fresh_store):
    s = _session(fresh_store)
    preview_apply(s, RemoveDuplicates(type="remove_duplicates"))
    ws.undo(s)
    with pytest.raises(AppError) as exc:
        ws.undo(s)
    assert exc.value.status == 409
    assert len(s.current) == 6


def test_reset_restores_original_and_clears_history(fresh_store):
    s = _session(fresh_store)
    original = s.original.copy()
    for op in [RemoveDuplicates(type="remove_duplicates"),
               StandardizeText(type="standardize_text", columns=["City"], case="upper"),
               FindReplace(type="find_replace", columns=["City"], find="LAHORE", replace="LHR")]:
        preview_apply(s, op)
    res = ws.reset(s)
    assert res["session"]["history"] == [] and res["session"]["can_undo"] is False
    assert res["session"]["current_shape"] == {"rows": 6, "columns": 5}
    pd.testing.assert_frame_equal(s.current, original)
    # Caches never serve stale results after reset or undo.
    assert ws.get_profile(s)["stats"]["duplicate_rows"] == 1
    assert ws.get_rows(s)["rows"][1][1] == "lahore"


def test_profile_cache_follows_undo(fresh_store):
    s = _session(fresh_store)
    assert ws.get_profile(s)["stats"]["duplicate_rows"] == 1
    preview_apply(s, RemoveDuplicates(type="remove_duplicates"))
    assert ws.get_profile(s)["stats"]["duplicate_rows"] == 0
    ws.undo(s)
    assert ws.get_profile(s)["stats"]["duplicate_rows"] == 1


def test_memory_budget_prunes_old_snapshots_but_keeps_last_undo(fresh_store, monkeypatch):
    monkeypatch.setattr(ws, "settings", dataclasses.replace(ws.settings, max_history_memory_mb=0))
    s = _session(fresh_store, "c\na\nb\n")
    for case in ["upper", "lower", "upper"]:
        preview_apply(s, StandardizeText(type="standardize_text", columns=["c"], case=case))
    flags = [h["undoable"] for h in ws.session_info(s)["history"]]
    assert flags == [False, True, True]
    assert s.can_undo
    ws.undo(s)
    assert s.current["c"].tolist() == ["a", "b"]
    assert not s.can_undo  # older step was pruned to respect the memory budget
    assert len(s.history) == 2  # but it is still listed in the activity log


def test_unchanged_columns_share_memory_between_versions(fresh_store):
    s = _session(fresh_store)
    preview_apply(s, StandardizeText(type="standardize_text", columns=["City"], case="upper"))
    entry = s.history[-1]
    from app.services.memory import frame_bytes
    assert 0 < entry.bytes < frame_bytes(s.current)


def test_light_profile_for_cleaning_forms(fresh_store):
    s = _session(fresh_store)
    light = ws.get_profile(s, light=True)
    full = ws.get_profile(s)
    assert light["light"] and light["issues"] == []
    assert [c["name"] for c in light["columns"]] == [c["name"] for c in full["columns"]]
    assert [c["type"] for c in light["columns"]] == [c["type"] for c in full["columns"]]
    assert light["stats"] == full["stats"]
