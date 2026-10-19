"""End-to-end HTTP tests through FastAPI's TestClient, using temporary files.

Every test talks to the real app: real parsing, real pandas operations, real
session store. Nothing is mocked except the size limit in the boundary tests
(set to 1 MB so they run quickly).
"""

import csv
import dataclasses
import io

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import responses as R  # noqa: E402

from .conftest import MESSY_CSV  # noqa: E402

client = TestClient(app)


@pytest.fixture
def messy_file(tmp_path):
    path = tmp_path / "people.csv"
    path.write_text(MESSY_CSV, encoding="utf-8")
    return path


def upload(body: str | bytes = MESSY_CSV, name: str = "people.csv", **params):
    data = body.encode("utf-8") if isinstance(body, str) else body
    return client.post("/api/upload", params={"filename": name, **params}, content=data,
                       headers={"Content-Type": "application/octet-stream"})


def session_headers(resp):
    assert resp.status_code == 201, resp.text
    return {"X-Session-Id": resp.json()["session_id"]}


def preview_then_apply(h, operation):
    p = client.post("/api/operations/preview", json={"operation": operation}, headers=h)
    assert p.status_code == 200, p.text
    a = client.post("/api/operations/apply", json={"operation": operation, "preview_token": p.json()["preview_token"]}, headers=h)
    assert a.status_code == 200, a.text
    return p.json(), a.json()


def error_code(resp):
    body = resp.json()
    assert set(body) == {"error"} and {"code", "message", "hint"} <= set(body["error"])
    assert "Traceback" not in resp.text
    return body["error"]["code"]


# ----------------------------------------------------------------- system

def test_health_config_and_security_headers():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    for header in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Content-Security-Policy"):
        assert header in r.headers
    cfg = client.get("/api/config").json()
    assert cfg["max_upload_mb"] == settings.max_upload_mb
    assert "csv" in cfg["formats"] and cfg["export_formats"] == ["csv", "xlsx"]


def test_openapi_documents_every_endpoint():
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/api/upload": {"post"}, "/api/session": {"get", "delete"}, "/api/profile": {"get"},
        "/api/rows": {"get"}, "/api/outliers": {"get"}, "/api/operations": {"get"},
        "/api/operations/preview": {"post"}, "/api/operations/apply": {"post"}, "/api/history": {"get"},
        "/api/undo": {"post"}, "/api/reset": {"post"}, "/api/compare": {"get"}, "/api/compare/rows": {"get"},
        "/api/export": {"get"}, "/api/health": {"get"}, "/api/config": {"get"}, "/api/values": {"get"},
        "/api/quick-clean/plan": {"get"}, "/api/quick-clean/preview": {"post"}, "/api/quick-clean/apply": {"post"},
        "/api/report": {"get"},
    }
    for path, methods in expected.items():
        assert methods <= set(paths[path]), path


# ----------------------------------------------------------------- upload

def test_upload_from_temporary_file(messy_file):
    r = upload(messy_file.read_bytes(), messy_file.name)
    assert r.status_code == 201
    data = R.UploadResponse.model_validate(r.json())
    assert data.file.name == "people.csv"
    assert data.current_shape.rows == 6 and data.current_shape.columns == 5
    assert data.history == [] and data.can_undo is False


@pytest.mark.parametrize("body,name,status,code", [
    (b"", "empty.csv", 400, "empty_file"),
    (b"   \n\n", "blank.csv", 400, "empty_file"),
    (b"a,b\n1,2\n", "data.pdf", 415, "invalid_extension"),
    (b"%PDF-1.4 hidden", "doc.csv", 415, "unsupported_content"),
    (b"a,b\n\x00\x01\x02", "bin.csv", 415, "binary_file"),
    (b'a,b\n"unclosed,1\n2,3\n' + b"x" * 10, "bad.csv", None, None),
    (b"PK\x03\x04junk", "bad.xlsx", 415, "corrupt_file"),
    (b"[{", "bad.json", 400, "invalid_json"),
])
def test_invalid_uploads_return_structured_errors(body, name, status, code):
    r = upload(body, name)
    if status is None:  # unbalanced quotes: either parsed safely or rejected clearly, never a 500
        assert r.status_code in (201, 400)
        return
    assert r.status_code == status
    assert error_code(r) == code


def test_header_only_and_duplicate_columns():
    r = upload("a,a,b\n", "header.csv")
    data = r.json()
    assert r.status_code == 201 and data["current_shape"] == {"rows": 0, "columns": 3}
    h = {"X-Session-Id": data["session_id"]}
    profile = client.get("/api/profile", headers=h).json()
    assert [c["name"] for c in profile["columns"]] == ["a", "a_2", "b"]
    assert profile["stats"]["completeness"] is None  # no cells: no meaningless percentage
    assert all(c["missing_pct"] is None for c in profile["columns"])


@pytest.fixture
def one_mb_limit(monkeypatch):
    from app.api.routers import sessions as sessions_router
    from app.services import workspace

    small = dataclasses.replace(settings, max_upload_mb=1)
    monkeypatch.setattr(sessions_router, "settings", small)
    monkeypatch.setattr(workspace, "settings", small)
    return 1024 * 1024


def _body(size: int) -> bytes:
    data = b"value\n" + b"x" * (size - 7) + b"\n"
    assert len(data) == size
    return data


def test_upload_at_and_below_limit(one_mb_limit):
    assert upload(_body(one_mb_limit - 1), "below.csv").status_code == 201
    assert upload(_body(one_mb_limit), "at.csv").status_code == 201


def test_upload_above_limit(one_mb_limit):
    r = upload(_body(one_mb_limit + 1), "above.csv")
    assert r.status_code == 413 and error_code(r) == "file_too_large"

    def stream():  # no Content-Length header: the server must still stop
        for _ in range(3):
            yield b"x" * (one_mb_limit // 2)
    r = client.post("/api/upload", params={"filename": "stream.csv"}, content=stream())
    assert r.status_code == 413


def test_upload_filename_is_sanitised():
    r = upload("a\n1\n", "..\\..\\secret\\data.csv")
    assert r.status_code == 201 and r.json()["file"]["name"] == "data.csv"


# ----------------------------------------------------------------- sessions

def test_session_isolation_and_token_validation():
    a = session_headers(upload("x\n1\n", "a.csv"))
    b = session_headers(upload("y\n2\n", "b.csv"))
    assert client.get("/api/rows", headers=a).json()["columns"][0]["name"] == "x"
    assert client.get("/api/rows", headers=b).json()["columns"][0]["name"] == "y"
    public_id, secret = a["X-Session-Id"].split(".")
    other_secret = b["X-Session-Id"].split(".")[1]
    tampered = secret[:-1] + ("B" if secret[-1] == "A" else "A")
    for bad in ["not-a-real-session", public_id, f"{public_id}.{other_secret}", f"{public_id}.{tampered}"]:
        r = client.get("/api/rows", headers={"X-Session-Id": bad})
        assert r.status_code == 404 and error_code(r) == "session_expired"
    r = client.get("/api/rows")
    assert r.status_code == 401 and error_code(r) == "no_session"


def test_session_details_and_delete():
    h = session_headers(upload())
    R.SessionInfo.model_validate(client.get("/api/session", headers=h).json())
    assert client.delete("/api/session", headers=h).status_code == 204
    assert client.get("/api/session", headers=h).status_code == 404
    assert client.delete("/api/session", headers=h).status_code == 204  # idempotent


def test_expired_session_is_rejected(monkeypatch):
    from app.services.sessions import store

    h = session_headers(upload())
    monkeypatch.setattr(store, "ttl", -1)
    r = client.get("/api/session", headers=h)
    assert r.status_code == 404 and error_code(r) == "session_expired"


# ----------------------------------------------------------------- inspection

def test_profile_statistics_are_calculated_from_the_file():
    h = session_headers(upload())
    p = R.Profile.model_validate(client.get("/api/profile", headers=h).json())
    assert p.stats.rows == 6 and p.stats.missing_cells == 3 and p.stats.duplicate_rows == 1
    assert p.stats.completeness == round(27 / 30 * 100, 2)
    age = next(c for c in p.columns if c.name == "Age")
    assert age.missing == 2 and age.type == "integer"
    assert {"duplicates", "missing:Age", "case:City"} <= {i.id for i in p.issues}
    light = client.get("/api/profile", headers=h, params={"light": True}).json()
    assert light["issues"] == [] and light["stats"] == p.stats.model_dump()


def test_rows_pagination_search_and_sort():
    h = session_headers(upload())
    page = client.get("/api/rows", headers=h, params={"page": 2, "page_size": 4}).json()
    assert page["total_pages"] == 2 and len(page["rows"]) == 2 and page["row_numbers"] == [5, 6]
    found = client.get("/api/rows", headers=h, params={"search": "LAHORE"}).json()
    assert found["total_rows"] == 4 and found["unfiltered_rows"] == 6
    s = client.get("/api/rows", headers=h, params={"sort_by": "Salary", "sort_dir": "desc"}).json()
    assert s["rows"][0][3] == "1000000" and s["rows"][-1][3] is None
    r = client.get("/api/rows", headers=h, params={"sort_by": "Nope"})
    assert r.status_code == 400 and error_code(r) == "unknown_columns"
    assert client.get("/api/rows", headers=h, params={"page": 0}).status_code == 422
    assert client.get("/api/rows", headers=h, params={"page_size": 10_000}).status_code == 422
    assert client.get("/api/rows", headers=h, params={"page_size": 1000}).json()["page_size"] == settings.max_page_size


def test_outliers_endpoint():
    h = session_headers(upload())
    r = client.get("/api/outliers", headers=h, params={"column": "Salary"})
    assert r.status_code == 200 and r.json()["count"] == 1 and r.json()["outliers"][0]["row"] == 5
    assert error_code(client.get("/api/outliers", headers=h, params={"column": "City"})) == "not_numeric"
    assert client.get("/api/outliers", headers=h, params={"column": "Missing"}).status_code == 404


# ----------------------------------------------------------------- operations

def test_operations_catalog():
    r = client.get("/api/operations")
    assert r.status_code == 200
    types = {o["type"]: o for o in r.json()}
    assert len(types) == 17 and types["remove_duplicates"]["may_remove_data"] is True
    assert types["trim_whitespace"]["may_remove_data"] is False


def test_preview_does_not_change_data():
    h = session_headers(upload())
    p = client.post("/api/operations/preview", json={"operation": {"type": "remove_duplicates", "keep": "first"}}, headers=h).json()
    assert p["rows_removed"] == 1 and p["destructive"] and p["changes"]["removed_rows"]["row_numbers"] == [3]
    assert client.get("/api/session", headers=h).json()["current_shape"]["rows"] == 6


def test_destructive_apply_requires_preview_token():
    h = session_headers(upload())
    op = {"type": "remove_duplicates", "keep": "first"}
    r = client.post("/api/operations/apply", json={"operation": op}, headers=h)
    assert r.status_code == 428 and error_code(r) == "preview_required"
    r = client.post("/api/operations/apply", json={"operation": op, "preview_token": "0" * 40}, headers=h)
    assert r.status_code == 409 and error_code(r) == "preview_outdated"
    assert client.get("/api/session", headers=h).json()["current_shape"]["rows"] == 6


def test_preview_token_is_bound_to_options_and_data_version():
    h = session_headers(upload())
    first = client.post("/api/operations/preview", json={"operation": {"type": "remove_duplicates", "keep": "first"}}, headers=h).json()
    # same token cannot be reused for different options
    r = client.post("/api/operations/apply", json={"operation": {"type": "remove_duplicates", "keep": "last"}, "preview_token": first["preview_token"]}, headers=h)
    assert r.status_code == 409
    # data changed after the preview -> token is outdated
    preview_then_apply(h, {"type": "trim_whitespace", "columns": []})
    r = client.post("/api/operations/apply", json={"operation": {"type": "remove_duplicates", "keep": "first"}, "preview_token": first["preview_token"]}, headers=h)
    assert r.status_code == 409


def test_non_destructive_apply_without_preview_is_allowed():
    h = session_headers(upload())
    r = client.post("/api/operations/apply", json={"operation": {"type": "standardize_text", "columns": ["City"], "case": "title"}}, headers=h)
    assert r.status_code == 200 and r.json()["applied"] and r.json()["cells_changed"] == 3


def _download(h, **params):
    r = client.get("/api/export", headers=h, params=params)
    assert r.status_code == 200, r.text
    return list(csv.reader(io.StringIO(r.content.decode("utf-8"))))


@pytest.mark.parametrize("operation,check", [
    ({"type": "remove_duplicates", "keep": "first"}, lambda rows: len(rows) == 6),
    ({"type": "trim_whitespace", "columns": []}, lambda rows: rows[1][0] == "Ali" and rows[0][0] == "Name "),
    ({"type": "standardize_text", "columns": ["City"], "case": "upper"}, lambda rows: {r[1] for r in rows[1:]} == {"LAHORE", "KARACHI", "ISLAMABAD"}),
    ({"type": "clean_column_names", "replace_spaces": True, "lowercase": True}, lambda rows: rows[0] == ["name", "city", "age", "salary", "joined"]),
    ({"type": "missing_values", "strategy": "fill_median", "columns": ["Age"]}, lambda rows: [r[2] for r in rows[1:]] == ["25", "28", "28", "31", "29", "27"]),
    ({"type": "missing_values", "strategy": "fill_constant", "columns": ["Salary"], "value": "0"}, lambda rows: rows[4][3] == "0"),
    ({"type": "missing_values", "strategy": "drop_rows", "columns": ["Age"]}, lambda rows: len(rows) == 5),
    ({"type": "convert_type", "columns": ["Joined"], "target": "datetime", "on_error": "set_missing"}, lambda rows: rows[4][4] == "" and rows[1][4] == "2024-01-05"),
    ({"type": "find_replace", "columns": ["City"], "find": "lahore", "replace": "LHR", "match": "exact"}, lambda rows: [r[1] for r in rows[1:]].count("LHR") == 2),
])
def test_each_operation_changes_the_exported_data(operation, check):
    h = session_headers(upload())
    _, applied = preview_then_apply(h, operation)
    R.ApplyResponse.model_validate(applied)
    assert applied["applied"] is True
    assert check(_download(h)), operation


def test_remove_empty_rows_and_columns_over_http():
    h = session_headers(upload("a,b,c\n1,,x\n,,\n2,,y\n", "empty.csv"))
    _, applied = preview_then_apply(h, {"type": "remove_empty", "target": "both"})
    assert applied["rows_removed"] == 1 and applied["columns_removed"] == 1
    assert _download(h) == [["a", "c"], ["1", "x"], ["2", "y"]]


def test_incompatible_operations_are_rejected():
    h = session_headers(upload())
    cases = [
        ({"type": "missing_values", "strategy": "fill_mean", "columns": ["City"]}, "not_numeric"),
        ({"type": "standardize_text", "columns": ["Nope"], "case": "lower"}, "unknown_columns"),
        ({"type": "missing_values", "strategy": "drop_rows", "columns": []}, "no_columns"),
        ({"type": "missing_values", "strategy": "fill_constant", "columns": ["Age"], "value": ""}, "missing_value"),
    ]
    for op, code in cases:
        r = client.post("/api/operations/preview", json={"operation": op}, headers=h)
        assert r.status_code == 400 and error_code(r) == code, op
    r = client.post("/api/operations/preview", json={"operation": {"type": "explode"}}, headers=h)
    assert r.status_code == 422 and error_code(r) == "invalid_request"
    r = client.post("/api/operations/preview", json={"operation": {"type": "trim_whitespace", "columns": [], "x": 1}}, headers=h)
    assert r.status_code == 422


def test_blocked_conversion_is_reported_not_applied():
    h = session_headers(upload())
    op = {"type": "convert_type", "columns": ["Joined"], "target": "datetime", "on_error": "abort"}
    p = client.post("/api/operations/preview", json={"operation": op}, headers=h).json()
    assert p["blocked"] and p["details"]["invalid_samples"][0]["value"] == "not a date"
    r = client.post("/api/operations/apply", json={"operation": op, "preview_token": p["preview_token"]}, headers=h)
    assert r.status_code == 422 and error_code(r) == "operation_blocked"
    assert client.get("/api/history", headers=h).json()["steps"] == []


def test_operation_that_changes_nothing_is_not_recorded():
    h = session_headers(upload("a\n1\n2\n", "u.csv"))
    _, applied = preview_then_apply(h, {"type": "remove_duplicates", "keep": "first"})
    assert applied["applied"] is False
    assert client.get("/api/history", headers=h).json()["log"] == []


# ----------------------------------------------------------------- history, undo, reset

def test_history_undo_and_reset_are_accurate():
    h = session_headers(upload())
    preview_then_apply(h, {"type": "remove_duplicates", "keep": "first"})
    preview_then_apply(h, {"type": "trim_whitespace", "columns": []})
    hist = R.HistoryResponse.model_validate(client.get("/api/history", headers=h).json())
    assert [s.type for s in hist.steps] == ["remove_duplicates", "trim_whitespace"] and hist.can_undo

    r = client.post("/api/undo", headers=h).json()
    assert r["undone"]["type"] == "trim_whitespace" and r["session"]["current_shape"]["rows"] == 5
    assert client.get("/api/rows", headers=h).json()["rows"][0][0] == "  Ali "  # trim really undone
    hist = client.get("/api/history", headers=h).json()
    assert [s["type"] for s in hist["steps"]] == ["remove_duplicates"]
    assert [e["event"] for e in hist["log"]] == ["applied", "applied", "undone"]

    r = client.post("/api/reset", headers=h).json()
    assert r["steps_removed"] == 1 and r["session"]["history"] == [] and r["session"]["current_shape"]["rows"] == 6
    hist = client.get("/api/history", headers=h).json()
    assert hist["steps"] == [] and hist["can_undo"] is False and hist["log"][-1]["event"] == "reset"
    r = client.post("/api/undo", headers=h)
    assert r.status_code == 409 and error_code(r) == "cannot_undo"
    assert _download(h) == list(csv.reader(io.StringIO(MESSY_CSV)))  # identical to the upload


# ----------------------------------------------------------------- compare & export

def test_compare_endpoints():
    h = session_headers(upload())
    preview_then_apply(h, {"type": "remove_duplicates", "keep": "first"})
    preview_then_apply(h, {"type": "missing_values", "strategy": "fill_constant", "columns": ["Salary"], "value": "0"})
    c = R.CompareResponse.model_validate(client.get("/api/compare", headers=h).json())
    assert c.original.rows == 6 and c.current.rows == 5 and c.rows_removed == 1
    assert c.original.missing_cells == 3 and c.current.missing_cells == 1 and c.cells_modified == 1
    rows = client.get("/api/compare/rows", headers=h, params={"changes_only": True}).json()
    by_row = {r["row"]: r for r in rows["rows"]}
    assert set(by_row) == {3, 4} and by_row[3]["current"] is None
    salary = rows["current_columns"].index("Salary")
    assert by_row[4]["changed"][salary] is True and by_row[4]["current"][salary] == "0"


def test_export_csv_and_excel():
    h = session_headers(upload('id,comment,city\n1,"Hello, ""world""",لاہور\n2,"two\nlines",\n', "notes.csv"))
    r = client.get("/api/export", headers=h, params={"filename": "../../clean me"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "clean me.csv" in r.headers["content-disposition"] and ".." not in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8"))))
    assert rows == [["id", "comment", "city"], ["1", 'Hello, "world"', "لاہور"], ["2", "two\nlines", ""]]
    assert client.get("/api/export", headers=h, params={"bom": True}).content.startswith(b"\xef\xbb\xbf")
    x = client.get("/api/export", headers=h, params={"format": "xlsx"})
    assert x.status_code == 200 and x.content.startswith(b"PK")
    assert client.get("/api/export", headers=h, params={"format": "pdf"}).status_code == 422


def test_other_formats_over_http(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    wb.active.append(["a", "b"])
    wb.active.append([1, "x"])
    path = tmp_path / "t.xlsx"
    wb.save(path)
    r = upload(path.read_bytes(), "t.xlsx")
    assert r.status_code == 201 and r.json()["file"]["format"] == "xlsx"
    j = upload(b'[{"a": 1}, {"a": 2}]', "t.json")
    assert j.status_code == 201 and j.json()["current_shape"] == {"rows": 2, "columns": 1}


# ----------------------------------------------------------------- robustness

def test_unexpected_errors_are_hidden(monkeypatch):
    from app.services import workspace

    h = session_headers(upload())

    def boom(*_a, **_k):
        raise RuntimeError("secret internal detail with cell value Ali")

    monkeypatch.setattr(workspace, "compare", boom)
    local = TestClient(app, raise_server_exceptions=False)
    r = local.get("/api/compare", headers=h)
    assert r.status_code == 500 and error_code(r) == "internal_error"
    assert "secret" not in r.text and "Ali" not in r.text


def test_rate_limiting(monkeypatch):
    from app.core import middleware

    monkeypatch.setattr(middleware, "settings", dataclasses.replace(settings, rate_limit_per_minute=3))
    middleware.rate_limiter._hits.clear()
    local = TestClient(app, client=("10.9.9.9", 1234))
    codes = [local.get("/api/health").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]


def test_unexpected_error_log_has_no_cell_values(monkeypatch, caplog):
    from app.services import workspace

    h = session_headers(upload())
    monkeypatch.setattr(workspace, "compare", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("cell value Ali")))
    local = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level("ERROR"):
        local.get("/api/compare", headers=h)
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "unexpected error" in logged and "ValueError" in logged and "Ali" not in logged


def test_upload_is_refused_when_too_many_run_at_once():
    from app.api.routers import sessions as sessions_router

    gate = sessions_router.upload_gate
    old = gate.limit
    gate.limit = 1
    assert gate.try_enter()  # simulate an upload in progress
    try:
        r = upload()
        assert r.status_code == 503 and error_code(r) == "server_busy"
    finally:
        gate.leave()
        gate.limit = old
    assert upload().status_code == 201


def test_force_https_redirects_only_proxied_http(monkeypatch):
    from app.core import middleware

    monkeypatch.setattr(middleware, "settings", dataclasses.replace(settings, force_https=True))
    r = client.get("/api/config", headers={"X-Forwarded-Proto": "http"}, follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"].startswith("https://")
    assert client.get("/api/config", headers={"X-Forwarded-Proto": "https"}).status_code == 200
    assert client.get("/api/config").status_code == 200  # direct (no proxy header)
    # Platform health probes are never redirected.
    assert client.get("/api/health", headers={"X-Forwarded-Proto": "http"}, follow_redirects=False).status_code == 200


def test_unknown_api_path_is_404_json():
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
