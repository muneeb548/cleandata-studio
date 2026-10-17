"""Regression tests for issues found in the QA/security audit."""

import csv
import io
import logging
import os
import time
import zipfile

import pytest

from app.core.errors import AppError
from app.services import workspace as ws
from app.services.profiling import detect_issues

from .conftest import load


def _session(store, text, name="a.csv"):
    info = ws.create_session(store, name, text.encode())
    return store.get(info["session_id"])


def test_access_log_hides_query_strings():
    from app.core.logging_utils import RedactQueryString

    rec = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4:5", "GET", "/api/rows?search=Ayesha%20Khan&sort_by=Salary", "1.1", 200), None)
    RedactQueryString().filter(rec)
    assert rec.getMessage() == '1.2.3.4:5 - "GET /api/rows?… HTTP/1.1" 200'
    assert "Ayesha" not in rec.getMessage()


def test_stale_temp_files_are_removed(tmp_path, monkeypatch):
    from app.utils import tempfiles

    monkeypatch.setattr(tempfiles.tempfile, "gettempdir", lambda: str(tmp_path))
    old = tmp_path / "cleandata_upload_old.csv"
    new = tmp_path / "cleandata_export_new.csv"
    other = tmp_path / "someone_elses_file.csv"
    for f in (old, new, other):
        f.write_text("x")
    past = time.time() - 7200
    os.utime(old, (past, past))
    os.utime(other, (past, past))
    assert tempfiles.remove_stale_temp_files() == 1
    assert not old.exists() and new.exists() and other.exists()  # never touches files that aren't ours


def test_xlsx_zip_bomb_is_rejected(tmp_path, monkeypatch):
    from app.services import importers

    path = tmp_path / "bomb.xlsx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/worksheets/sheet1.xml", b"0" * (3 * 1024 * 1024))  # compresses ~1000x
    monkeypatch.setattr(importers, "MAX_XLSX_EXPANDED_BYTES", 2 * 1024 * 1024)
    with pytest.raises(AppError) as exc:
        importers.load_file(str(path), "bomb.xlsx")
    assert exc.value.status == 413


def test_xlsx_requires_defusedxml(tmp_path, monkeypatch):
    import openpyxl
    import openpyxl.xml

    path = tmp_path / "ok.xlsx"
    wb = openpyxl.Workbook()
    wb.active.append(["a"])
    wb.save(path)
    monkeypatch.setattr(openpyxl.xml, "DEFUSEDXML", False)
    from app.services import importers

    with pytest.raises(AppError) as exc:
        importers.load_file(str(path), "ok.xlsx")
    assert exc.value.code == "missing_dependency"


def test_too_many_columns_is_rejected(fresh_store):
    text = ",".join(f"c{i}" for i in range(ws.MAX_COLUMNS + 1)) + "\n" + ",".join("1" for _ in range(ws.MAX_COLUMNS + 1)) + "\n"
    with pytest.raises(AppError) as exc:
        ws.create_session(fresh_store, "wide.csv", text.encode())
    assert exc.value.code == "too_many_columns"
    assert len(fresh_store) == 0


def test_placeholder_issue_reports_the_real_token():
    df = load("a\nnull\nnull\n-\nok\n").df
    issue = next(i for i in detect_issues(df) if i["id"] == "placeholder:a")
    assert issue["example"] == "null" and '"null"' in issue["description"]


def test_formula_like_text_is_flagged_and_can_be_escaped(fresh_store):
    s = _session(fresh_store, 'cmd,amount\n=HYPERLINK("http://x"),-3.5\n@SUM(A1),+5\nhello,7\n')
    issue = next(i for i in detect_issues(s.current) if i["id"] == "formula:cmd")
    assert issue["count"] == 2
    assert not any(i["id"] == "formula:amount" for i in detect_issues(s.current))  # numbers are not formulas

    plain, _, _ = ws.export_file(s, None, "csv")
    safe, _, _ = ws.export_file(s, None, "csv", protect_formulas=True)
    try:
        with open(plain, encoding="utf-8") as f:
            assert next(r for r in csv.reader(f) if r[0].startswith("=")) == ['=HYPERLINK("http://x")', "-3.5"]
        with open(safe, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert rows[1] == ["'=HYPERLINK(\"http://x\")", "-3.5"] and rows[2] == ["'@SUM(A1)", "+5"]
    finally:
        os.remove(plain)
        os.remove(safe)
    assert s.current.loc[0, "cmd"].startswith("=")  # the data itself is never changed by escaping


def test_issue_ids_are_unique_on_messy_data():
    df = load("a ,a ,b\n x,=1,null\n x,=1,null\n,,\n").df
    ids = [i["id"] for i in detect_issues(df)]
    assert len(ids) == len(set(ids))


def test_export_round_trip_of_tricky_text(fresh_store):
    text = 'id,txt\n1,"a, b"\n2,"say ""hi"""\n3,"multi\nline"\n4,محمد 😀\n5," lead"\n'
    s = _session(fresh_store, text)
    out = ws.export_csv(s)[0].decode()
    # Values survive exactly; quoting may be normalised (" lead" needs no quotes).
    assert list(csv.reader(io.StringIO(out))) == list(csv.reader(io.StringIO(text)))
    assert list(csv.reader(io.StringIO(out)))[3] == ["3", "multi\nline"]
