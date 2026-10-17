"""Cleaning history, undo and reset."""

from fastapi import APIRouter

from app.api.deps import SESSION_ERRORS, SessionDep
from app.schemas.responses import ErrorResponse, HistoryResponse, ResetResponse, UndoResponse
from app.services import workspace

router = APIRouter(tags=["history"])


@router.get("/history", response_model=HistoryResponse, summary="Cleaning history and audit log", responses=SESSION_ERRORS)
def history(session: SessionDep) -> dict:
    return workspace.history(session)


@router.post(
    "/undo",
    response_model=UndoResponse,
    summary="Undo the last operation",
    responses={**SESSION_ERRORS, 409: {"model": ErrorResponse, "description": "Nothing to undo."}},
)
def undo(session: SessionDep) -> dict:
    return workspace.undo(session)


@router.post("/reset", response_model=ResetResponse, summary="Reset to the original upload", responses=SESSION_ERRORS)
def reset(session: SessionDep) -> dict:
    return workspace.reset(session)
