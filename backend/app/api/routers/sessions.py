"""Upload a file (creates a session), inspect and delete the session."""

from __future__ import annotations

import os
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.api.deps import SESSION_ERRORS, SessionDep
from app.core.config import settings
from app.core.errors import AppError
from app.core.security import ConcurrencyGate
from app.schemas.responses import ErrorResponse, SessionInfo, UploadResponse
from app.services import workspace
from app.services.importers import validate_filename
from app.services.sessions import store

router = APIRouter(tags=["sessions"])

# Importing a file briefly needs several times its size in memory, so the number of
# simultaneous imports can be limited (MAX_CONCURRENT_UPLOADS; 0 = unlimited).
upload_gate = ConcurrencyGate(settings.max_concurrent_uploads)


def _too_large() -> AppError:
    return AppError("file_too_large", f"The file is larger than the {settings.max_upload_mb} MB limit.",
                    "Split the file into smaller parts or remove unneeded columns.", status=413)


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=UploadResponse,
    summary="Upload a data file and start a session",
    responses={
        400: {"model": ErrorResponse, "description": "Empty, malformed or unreadable file."},
        413: {"model": ErrorResponse, "description": "File larger than MAX_UPLOAD_MB."},
        415: {"model": ErrorResponse, "description": "Unsupported or corrupted file type."},
        503: {"model": ErrorResponse, "description": "Server busy (too many uploads or datasets at once)."},
        507: {"model": ErrorResponse, "description": "Not enough memory to load the file."},
    },
)
async def upload(
    request: Request,
    filename: Annotated[str, Query(max_length=255, description="Original file name, e.g. customers.csv")],
    format: Annotated[Literal["csv", "tsv", "xlsx", "xls", "json"] | None, Query(description="Override format detection.")] = None,
    sheet: Annotated[str | None, Query(max_length=255, description="Excel sheet to load (default: first).")] = None,
) -> dict:
    """Send the raw file bytes as the request body (`Content-Type: application/octet-stream`).

    The body is streamed to a private temporary file and the upload stops as
    soon as it passes the size limit. The temporary file is deleted as soon as
    the import finishes or fails; the data then lives only in memory.
    """
    limit = settings.max_upload_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise _too_large()
    safe_name = validate_filename(filename)
    if not upload_gate.try_enter():
        raise AppError("server_busy", "The server is processing other uploads right now.",
                       "Please try again in a minute.", status=503)
    path = workspace.temp_upload_path(safe_name)
    size = 0
    try:
        with open(path, "wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise _too_large()
                out.write(chunk)
        if size == 0:
            raise AppError("empty_file", "The file is empty.", "Check that you exported the data correctly and try again.")
        return await run_in_threadpool(
            workspace.create_session_from_path, store, safe_name, path, size, format, sheet or None
        )
    except ClientDisconnect:
        raise AppError("upload_cancelled", "The upload was cancelled.", None, status=400)
    finally:
        upload_gate.leave()
        try:
            os.remove(path)
        except OSError:
            pass


@router.get("/session", response_model=SessionInfo, summary="Session details and history", responses=SESSION_ERRORS)
def get_session(session: SessionDep) -> dict:
    return workspace.session_info(session)


@router.delete(
    "/session",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete the session and its data",
)
def end_session(x_session_id: Annotated[str | None, Header(max_length=100)] = None) -> Response:
    """Idempotent: returns 204 whether or not the session still existed."""
    store.delete(x_session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
