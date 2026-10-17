"""FastAPI application entry point.

Run locally:      uvicorn app.main:app --reload --port 8000
Run in production (one worker — sessions live in this process's memory):
                  uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --no-server-header
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.core.config import settings
from app.core.logging_utils import RedactQueryString
from app.utils.tempfiles import remove_stale_temp_files
from app.core.errors import AppError
from app.core.middleware import guard
from app.services.sessions import store
from app.web import FrontendFiles

# Logs contain event names, sizes and counts only. Cell values and file
# contents are never logged.
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cleandata")

_problems = settings.problems()
if _problems and settings.is_production:
    # Refuse to start with an unsafe production configuration (shown in the platform's logs).
    raise RuntimeError("Invalid production configuration:\n- " + "\n- ".join(_problems))
for _problem in _problems:
    log.warning("configuration: %s", _problem)


logging.getLogger("uvicorn.access").addFilter(RedactQueryString())


async def _cleanup_loop() -> None:
    remove_stale_temp_files()
    while True:
        await asyncio.sleep(60)
        removed = store.cleanup()
        if removed:
            log.info("expired %d inactive session(s)", removed)
        stale = remove_stale_temp_files()
        if stale:
            log.info("removed %d stale temporary file(s)", stale)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Settings only, never data. Makes it easy to confirm in the logs what is running.
    log.info(
        "starting: environment=%s max_upload_mb=%d session_ttl_minutes=%d max_sessions=%d "
        "max_total_memory_mb=%d max_concurrent_uploads=%d api_docs=%s frontend=%s",
        settings.environment, settings.max_upload_mb, settings.session_ttl_minutes, settings.max_sessions,
        settings.max_total_memory_mb, settings.max_concurrent_uploads, settings.enable_api_docs,
        "served" if frontend and frontend.available else "not served",
    )
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()


frontend = FrontendFiles(settings.frontend_dist) if settings.frontend_dist else None

app = FastAPI(
    title="CleanData Studio API",
    version="1.0.0",
    description="Upload, inspect, clean and export CSV datasets. Data is kept in memory only.",
    lifespan=lifespan,
    # The interactive docs are handy locally; in production they are off by default.
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Session-Id"],
    expose_headers=["Content-Disposition"],
)


app.middleware("http")(guard)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    log.info("request rejected: %s", exc.code)
    return JSONResponse(status_code=exc.status, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    problems = []
    for err in exc.errors()[:5]:
        location = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query", "operation"))
        problems.append(f"{location}: {err.get('msg')}" if location else str(err.get("msg")))
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "invalid_request", "message": "Some options are invalid.",
                           "hint": "; ".join(problems)}},
    )


@app.exception_handler(Exception)
async def unexpected_handler(request: Request, exc: Exception):
    error_id = uuid.uuid4().hex[:8]
    # Log the exception type, route and code location only: messages and full
    # tracebacks may contain cell values. Search the logs for "unexpected error".
    tb = exc.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    where = f"{os.path.basename(tb.tb_frame.f_code.co_filename)}:{tb.tb_lineno}" if tb else "?"
    log.error("unexpected error %s: %s at %s (%s %s)", error_id, type(exc).__name__, where,
              request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error",
                           "message": "Something went wrong while processing your request.",
                           "hint": f"Try again. If it keeps happening, report error id {error_id}."}},
    )


app.include_router(api_router)

# Optionally serve the built website from the same server (one origin: no CORS needed).
if frontend is not None:
    if frontend.available:
        @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
        async def website(path: str):
            return frontend.response(path)
    else:
        log.warning("FRONTEND_DIST is set but %s/index.html was not found; the website is not served", frontend.root)
