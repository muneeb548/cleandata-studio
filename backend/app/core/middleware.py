"""HTTP middleware: HTTPS redirect, rate limiting and security headers.

Starlette-only (no FastAPI import), so it can be tested and reused on its own.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from app.core.config import settings
from app.core.security import client_ip, rate_limiter, response_headers


async def guard(request: Request, call_next):
    if (settings.force_https and request.url.path != "/api/health"
            and request.headers.get("x-forwarded-proto", "").lower() == "http"):
        # Uses the hosting proxy's header. The health check is never redirected, so a
        # platform health probe over plain HTTP still gets 200.
        return RedirectResponse(str(request.url.replace(scheme="https")), status_code=308)
    client = client_ip(request.client.host if request.client else None, request.headers, settings.client_ip_header)
    is_upload = request.url.path == "/api/upload"
    limit = settings.upload_limit_per_minute if is_upload else settings.rate_limit_per_minute
    if request.method != "OPTIONS" and not rate_limiter.allow(f"{client}:{'u' if is_upload else 'a'}", limit):
        response = JSONResponse(
            status_code=429,
            content={"error": {"code": "rate_limited", "message": "Too many requests.",
                               "hint": "Wait a minute and try again."}},
        )
    else:
        response = await call_next(request)
    is_docs = request.url.path in ("/docs", "/redoc", "/openapi.json") or request.url.path.startswith("/docs/")
    # setdefault: website files set their own Cache-Control and Content-Security-Policy.
    for key, value in response_headers(hsts_seconds=settings.hsts_seconds, is_docs=is_docs).items():
        response.headers.setdefault(key, value)
    return response
