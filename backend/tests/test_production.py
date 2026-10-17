"""Production configuration: settings validation, headers, client IP, capacity limits
and serving the built website. None of these need FastAPI."""

from __future__ import annotations

import time

import pandas as pd
import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import HTML_CSP, ConcurrencyGate, client_ip, response_headers
from app.services.sessions import SessionStore
from app.web import FrontendFiles


# ----------------------------------------------------------------- settings

def test_production_rejects_wildcard_and_http_origins():
    s = Settings(environment="production", cors_origins=["*", "http://example.com"])
    problems = s.problems()
    assert any("'*' is not allowed" in p for p in problems)
    assert any("http://example.com" in p for p in problems)


def test_production_accepts_https_origin():
    assert Settings(environment="production", cors_origins=["https://cleandata.example.com"]).problems() == []


def test_production_tolerates_localhost_for_local_rehearsal():
    assert Settings(environment="production", cors_origins=["http://localhost:5173"]).problems() == []


def test_development_allows_localhost():
    assert Settings(environment="development").problems() == []


def test_unknown_environment_is_reported():
    assert Settings(environment="prod").problems()


# ------------------------------------------------------------------ headers

def test_hsts_only_when_configured():
    assert "Strict-Transport-Security" not in response_headers(hsts_seconds=0)
    assert response_headers(hsts_seconds=31536000)["Strict-Transport-Security"] == "max-age=31536000"


def test_docs_have_no_csp_but_api_does():
    assert "Content-Security-Policy" not in response_headers(is_docs=True)
    assert response_headers()["Content-Security-Policy"].startswith("default-src 'none'")


def test_html_csp_allows_only_same_origin_scripts():
    assert "script-src 'self';" in HTML_CSP
    assert "unsafe-eval" not in HTML_CSP
    assert "frame-ancestors 'none'" in HTML_CSP


# ---------------------------------------------------------------- client ip

def test_client_ip_defaults_to_connection_address():
    assert client_ip("10.0.0.5", {"x-real-ip": "1.2.3.4"}, "") == "10.0.0.5"


def test_client_ip_uses_configured_header():
    assert client_ip("100.64.0.1", {"x-real-ip": "203.0.113.9"}, "x-real-ip") == "203.0.113.9"


def test_forwarded_for_uses_rightmost_entry():
    # The left part can be typed by the client; the right-most entry was added by the proxy.
    headers = {"x-forwarded-for": "6.6.6.6, 203.0.113.9"}
    assert client_ip("100.64.0.1", headers, "X-Forwarded-For") == "203.0.113.9"


@pytest.mark.parametrize("value", ["", "not-an-ip", "999.1.1.1", " , "])
def test_invalid_header_falls_back(value):
    assert client_ip("100.64.0.1", {"x-real-ip": value}, "x-real-ip") == "100.64.0.1"


# ------------------------------------------------------------ upload gate

def test_concurrency_gate():
    gate = ConcurrencyGate(2)
    assert gate.try_enter() and gate.try_enter()
    assert not gate.try_enter()
    gate.leave()
    assert gate.try_enter()
    unlimited = ConcurrencyGate(0)
    assert all(unlimited.try_enter() for _ in range(100))


# ------------------------------------------------------- memory / capacity

def _frame(rows: int) -> pd.DataFrame:
    return pd.DataFrame({"a": pd.array([f"value-{i}" for i in range(rows)], dtype="string")})


def _create(store: SessionStore, rows: int):
    return store.create(filename="f.csv", file_size=1, encoding="utf-8", delimiter=",",
                        import_warnings=[], original=_frame(rows))


def _one_size() -> int:
    probe = SessionStore(ttl_seconds=600, max_sessions=10, max_total_bytes=10**9)
    return _create(probe, 1000)[0].original_bytes


def test_memory_budget_removes_idle_sessions_first():
    store = SessionStore(ttl_seconds=600, max_sessions=10, max_total_bytes=int(_one_size() * 1.5))
    first, _ = _create(store, 1000)
    second, _ = _create(store, 1000)  # doesn't fit next to the first: the least recently used is removed
    assert len(store) == 1 and second.id in store._sessions and first.id not in store._sessions


def test_memory_budget_refuses_instead_of_removing_active_sessions():
    store = SessionStore(ttl_seconds=600, max_sessions=10, max_total_bytes=int(_one_size() * 1.5), protect_seconds=300)
    _create(store, 1000)
    with pytest.raises(AppError) as err:
        _create(store, 1000)
    assert err.value.status == 503 and err.value.code == "server_busy"
    assert len(store) == 1  # the first user's data was not taken away


def test_protected_session_becomes_removable_after_idle_window():
    store = SessionStore(ttl_seconds=600, max_sessions=1, protect_seconds=300)
    first, _ = _create(store, 10)
    with pytest.raises(AppError):
        _create(store, 10)
    first.last_access = time.time() - 301
    _create(store, 10)
    assert first.id not in store._sessions


def test_dataset_larger_than_whole_budget_is_413():
    store = SessionStore(ttl_seconds=600, max_sessions=10, max_total_bytes=100)
    with pytest.raises(AppError) as err:
        _create(store, 1000)
    assert err.value.status == 413


def test_without_budget_behaviour_is_unchanged():
    store = SessionStore(ttl_seconds=600, max_sessions=2)
    a, _ = _create(store, 5)
    _create(store, 5)
    _create(store, 5)  # least recently used is removed, as before
    assert a.id not in store._sessions and len(store) == 2


# --------------------------------------------------------- website files

@pytest.fixture
def dist(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>x</title>")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "robots.txt").write_text("User-agent: *")
    (tmp_path.parent / "secret.txt").write_text("outside")
    return FrontendFiles(tmp_path)


def test_known_pages_get_the_app_with_csp(dist):
    for path in ("", "app", "about/", "privacy", "contact"):
        r = dist.response(path)
        assert r.status_code == 200 and r.path == dist.index
        assert r.headers["content-security-policy"] == HTML_CSP
        assert r.headers["cache-control"] == "no-cache"


def test_unknown_page_gets_app_with_404(dist):
    r = dist.response("does-not-exist")
    assert r.status_code == 404 and r.path == dist.index


def test_hashed_assets_are_cached_long(dist):
    r = dist.response("assets/index-abc123.js")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    assert dist.response("assets/old-file.js").status_code == 404


def test_other_static_files(dist):
    r = dist.response("robots.txt")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=3600"


def test_unknown_api_path_is_json_404(dist):
    r = dist.response("api/nope")
    assert r.status_code == 404 and b"not_found" in r.body


@pytest.mark.parametrize("path", ["../secret.txt", "assets/../../secret.txt", "%2e%2e/secret.txt", "a\x00b"])
def test_path_traversal_is_blocked(dist, path):
    r = dist.response(path)
    assert getattr(r, "path", None) in (None, dist.index)


# ------------------------------------------------------------- middleware

def _run_guard(monkeypatch, path="/api/config", headers=None, **overrides):
    import asyncio
    import dataclasses

    from starlette.requests import Request
    from starlette.responses import JSONResponse

    from app.core import middleware
    from app.core.config import settings

    monkeypatch.setattr(middleware, "settings", dataclasses.replace(settings, **overrides))
    scope = {"type": "http", "method": "GET", "path": path, "query_string": b"", "scheme": "http",
             "server": ("app.example.com", 80), "client": ("100.64.0.9", 5555),
             "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]}

    async def call_next(_request):
        return JSONResponse({"ok": True})

    return asyncio.run(middleware.guard(Request(scope), call_next))


def test_guard_adds_security_headers_and_hsts(monkeypatch):
    r = _run_guard(monkeypatch, hsts_seconds=600)
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["strict-transport-security"] == "max-age=600"
    assert r.headers["cache-control"] == "no-store"


def test_guard_https_redirect(monkeypatch):
    r = _run_guard(monkeypatch, headers={"X-Forwarded-Proto": "http"}, force_https=True)
    assert r.status_code == 308 and r.headers["location"] == "https://app.example.com/api/config"
    health = _run_guard(monkeypatch, path="/api/health", headers={"X-Forwarded-Proto": "http"}, force_https=True)
    assert health.status_code == 200


def test_guard_rate_limits_per_visitor_behind_proxy(monkeypatch):
    from app.core import middleware

    middleware.rate_limiter._hits.clear()
    codes_a = [_run_guard(monkeypatch, headers={"X-Real-IP": "203.0.113.1"}, rate_limit_per_minute=2,
                          client_ip_header="X-Real-IP").status_code for _ in range(3)]
    # Same proxy address, different visitor: has its own budget.
    code_b = _run_guard(monkeypatch, headers={"X-Real-IP": "203.0.113.2"}, rate_limit_per_minute=2,
                        client_ip_header="X-Real-IP").status_code
    assert codes_a == [200, 200, 429] and code_b == 200
    middleware.rate_limiter._hits.clear()
