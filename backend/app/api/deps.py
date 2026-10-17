"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header

from app.schemas.responses import ErrorResponse
from app.services.sessions import Session, store


def get_session(
    x_session_id: Annotated[
        str | None,
        Header(description="Session token returned by POST /api/upload (format: <id>.<secret>).", max_length=100),
    ] = None,
) -> Session:
    """Resolve and verify the session token. Raises 401 if missing, 404 if unknown, invalid or expired."""
    return store.get(x_session_id)


SessionDep = Annotated[Session, Depends(get_session)]

# Error responses shared by session-bound endpoints (for the OpenAPI docs).
SESSION_ERRORS = {
    401: {"model": ErrorResponse, "description": "No session token was sent."},
    404: {"model": ErrorResponse, "description": "The session does not exist, the token is invalid, or it expired."},
}
VALIDATION_ERROR = {422: {"model": ErrorResponse, "description": "Invalid parameters, or the operation cannot be applied."}}
