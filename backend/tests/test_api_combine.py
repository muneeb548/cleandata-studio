"""Combine files over HTTP: POST/GET/DELETE /api/files and the combine_files operation."""

import dataclasses

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import responses as R  # noqa: E402

client = TestClient(app)

CUSTOMERS = "id,name,email\n1,Ali,ali@x.com\n2,Sara,sara@x.com\n"
ORDERS = "Email,amount\nALI@x.com,100\n"
MORE = "id,name,email\n3,Omar,omar@x.com\n"


def post_file(path, body, name, headers=None, **params):
    return client.post(path, params={"filename": name, **params}, content=body.encode(),
                       headers={"Content-Type": "application/octet-stream", **(headers or {})})


@pytest.fixture
def h():
    resp = post_file("/api/upload", CUSTOMERS, "customers.csv")
    assert resp.status_code == 201, resp.text
    return {"X-Session-Id": resp.json()["session_id"]}


def add(h, body=ORDERS, name="orders.csv"):
    resp = post_file("/api/files", body, name, h)
    assert resp.status_code == 201, resp.text
    R.AttachResponse.model_validate(resp.json())
    return resp.json()["file"]["id"]


def preview_then_apply(h, operation):
    p = client.post("/api/operations/preview", json={"operation": operation}, headers=h)
    assert p.status_code == 200, p.text
    R.OperationPreview.model_validate(p.json())
    a = client.post("/api/operations/apply", json={"operation": operation, "preview_token": p.json()["preview_token"]},
                    headers=h)
    assert a.status_code == 200, a.text
    R.ApplyResponse.model_validate(a.json())
    return p.json(), a.json()


def test_add_preview_and_remove_file(h):
    fid = add(h)
    info = client.get("/api/session", headers=h).json()
    assert [f["name"] for f in info["files"]] == ["orders.csv"]
    preview = client.get(f"/api/files/{fid}", headers=h)
    assert preview.status_code == 200
    R.AttachedFilePreview.model_validate(preview.json())
    assert preview.json()["preview"]["rows"] == [["ALI@x.com", "100"]]
    gone = client.delete(f"/api/files/{fid}", headers=h)
    assert gone.status_code == 200 and gone.json()["files"] == []
    assert client.get(f"/api/files/{fid}", headers=h).status_code == 404


def test_file_endpoints_need_a_session():
    assert post_file("/api/files", ORDERS, "orders.csv").status_code == 401
    assert client.get("/api/files/abc").status_code == 401


def test_files_are_private_to_their_session(h):
    fid = add(h)
    other = {"X-Session-Id": post_file("/api/upload", CUSTOMERS, "c.csv").json()["session_id"]}
    assert client.get(f"/api/files/{fid}", headers=other).status_code == 404
    op = {"type": "combine_files", "file_id": fid, "mode": "append"}
    resp = client.post("/api/operations/preview", json={"operation": op}, headers=other)
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "file_not_found"


def test_bad_file_ids_are_rejected(h):
    assert client.get("/api/files/..%2Fsecret", headers=h).status_code in (404, 422)
    assert client.delete("/api/files/" + "x" * 65, headers=h).status_code == 422


def test_added_file_obeys_upload_limit(h, monkeypatch):
    from app.api.routers import files as files_router
    from app.services import workspace

    small = dataclasses.replace(settings, max_upload_mb=1)
    monkeypatch.setattr(files_router, "settings", small)
    monkeypatch.setattr(workspace, "settings", small)
    resp = post_file("/api/files", "a\n" + "x" * (1024 * 1024 + 10), "big.csv", h)
    assert resp.status_code == 413 and resp.json()["error"]["code"] == "file_too_large"


def test_empty_added_file(h):
    resp = post_file("/api/files", "", "empty.csv", h)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "empty_file"


def test_append_then_undo(h):
    fid = add(h, MORE, "more.csv")
    _, applied = preview_then_apply(h, {"type": "combine_files", "file_id": fid, "mode": "append"})
    assert applied["applied"] and applied["session"]["current_shape"]["rows"] == 3
    rows = client.get("/api/rows", headers=h).json()
    assert [r[1] for r in rows["rows"]] == ["Ali", "Sara", "Omar"]
    assert client.post("/api/undo", headers=h).status_code == 200
    assert client.get("/api/session", headers=h).json()["current_shape"]["rows"] == 2


def test_join_and_download(h):
    fid = add(h)
    op = {"type": "combine_files", "file_id": fid, "mode": "join", "keys": [{"left": "email", "right": "Email"}]}
    preview, _ = preview_then_apply(h, op)
    assert preview["details"]["matched_rows"] == 1
    csv = client.get("/api/export", params={"format": "csv"}, headers=h).text
    assert csv.splitlines() == ["id,name,email,amount", "1,Ali,ali@x.com,100", "2,Sara,sara@x.com,"]


def test_inner_join_requires_preview(h):
    fid = add(h)
    op = {"type": "combine_files", "file_id": fid, "mode": "join", "how": "inner",
          "keys": [{"left": "email", "right": "Email"}]}
    resp = client.post("/api/operations/apply", json={"operation": op}, headers=h)
    assert resp.status_code == 428


def test_operations_catalog_lists_combine():
    catalog = client.get("/api/operations").json()
    assert any(o["type"] == "combine_files" for o in catalog)
