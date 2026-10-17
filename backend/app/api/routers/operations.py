"""Cleaning operations: catalog, preview and apply."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SESSION_ERRORS, VALIDATION_ERROR, SessionDep
from app.schemas.operations import OperationRequest
from app.schemas.responses import ApplyResponse, ErrorResponse, OperationInfo, OperationPreview
from app.services import workspace

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("", response_model=list[OperationInfo], summary="List available cleaning operations")
def list_operations() -> list[dict]:
    """Each operation with its parameters as JSON Schema, generated from the request models."""
    return workspace.operations_catalog()


@router.post("/preview", response_model=OperationPreview, summary="Preview an operation", responses={**SESSION_ERRORS, **VALIDATION_ERROR})
def preview(body: OperationRequest, session: SessionDep) -> dict:
    """Runs the operation on the working data without saving it and reports exactly
    what would change. Returns a `preview_token` for the apply request."""
    return workspace.preview_operation(session, body.operation)


@router.post(
    "/apply",
    response_model=ApplyResponse,
    summary="Apply an operation",
    responses={
        **SESSION_ERRORS,
        **VALIDATION_ERROR,
        409: {"model": ErrorResponse, "description": "preview_token is outdated (data or options changed)."},
        428: {"model": ErrorResponse, "description": "The operation can remove data and was not previewed."},
    },
)
def apply(body: OperationRequest, session: SessionDep) -> dict:
    """Applies the operation and records it in the history. Operations that can remove
    rows or columns require the `preview_token` from a preview of the same operation."""
    return workspace.apply_operation(session, body.operation, body.preview_token)
