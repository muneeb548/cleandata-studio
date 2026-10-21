"""Other files added to a session, so they can be combined with the working data (Combine files)."""

from __future__ import annotations

import os
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.api.deps import SESSION_ERRORS, SessionDep
from app.api.routers.sessions import _too_large, upload_gate
from app.core.config import settings
from app.core.errors import AppError
from app.schemas.responses import AttachedFilePreview, AttachResponse, ErrorResponse, SessionInfo
from app.services import workspace
from app.services.importers import validate_filename
from app.services.sessions import store

router = APIRouter(prefix="/files", tags=["combine files"])

FileId = Annotated[str, Path(max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AttachResponse,
    summary="Add another file to combine with the working data",
    responses={
        **SESSION_ERRORS,
        400: {"model": ErrorResponse, "description": "Empty, malformed or unreadable file."},
        409: {"model": ErrorResponse, "description": "Too many files added to this session."},
        413: {"model": ErrorResponse, "description": "File larger than MAX_UPLOAD_MB."},
        415: {"model": ErrorResponse, "description": "Unsupported or corrupted file type."},
        503: {"model": ErrorResponse, "description": "Server busy."},
        507: {"model": ErrorResponse, "description": "Not enough memory to load the file."},
    },
)
async def add_file(
    request: Request,
    session: SessionDep,
    filename: Annotated[str, Query(max_length=255, description="Original file name, e.g. orders.csv")],
    format: Annotated[Literal["csv", "tsv", "xlsx", "xls", "json"] | None, Query(description="Override format detection.")] = None,
    sheet: Annotated[str | None, Query(max_length=255, description="Excel sheet to load (default: first).")] = None,
) -> dict:
    """Send the raw file bytes as the request body, exactly like `POST /api/upload`.

    The file gets the same validation and size limit as the main upload. It is kept
    in memory only, is never cleaned itself, and is deleted with the session."""
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
            workspace.attach_file_from_path, store, session, safe_name, path, size, format, sheet or None
        )
    except ClientDisconnect:
        raise AppError("upload_cancelled", "The upload was cancelled.", None, status=400)
    finally:
        upload_gate.leave()
        try:
            os.remove(path)
        except OSError:
            pass


@router.get("/{file_id}", response_model=AttachedFilePreview, summary="First rows of an added file",
            responses=SESSION_ERRORS)
def get_file(file_id: FileId, session: SessionDep,
             rows: Annotated[int, Query(ge=1, le=50)] = 10) -> dict:
    return workspace.preview_file(session, file_id, rows)


@router.delete("/{file_id}", response_model=SessionInfo, summary="Remove an added file", responses=SESSION_ERRORS)
def delete_file(file_id: FileId, session: SessionDep) -> dict:
    """Steps already applied with this file keep their result and can still be undone."""
    return workspace.remove_file(session, file_id)
