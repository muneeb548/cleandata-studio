"""Quick Clean (safe fixes in one go) and the change report for the client."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SESSION_ERRORS, VALIDATION_ERROR, SessionDep
from app.schemas.operations import QuickCleanRequest
from app.schemas.responses import ChangeReport, ErrorResponse, QuickCleanPlan, QuickCleanPreview, QuickCleanResult, Recipe
from app.services import workspace

router = APIRouter(tags=["quick clean"])


@router.get("/quick-clean/plan", response_model=QuickCleanPlan, summary="Safe fixes for the working data", responses=SESSION_ERRORS)
def plan(session: SessionDep) -> dict:
    """Fixes that keep the meaning of the data, each with what it would change, plus the
    things that need a person's decision and are therefore not changed."""
    return workspace.quick_clean_plan(session)


@router.post("/quick-clean/preview", response_model=QuickCleanPreview, summary="Preview several fixes together",
             responses={**SESSION_ERRORS, **VALIDATION_ERROR})
def preview(body: QuickCleanRequest, session: SessionDep) -> dict:
    return workspace.preview_quick_clean(session, body.operations)


@router.post(
    "/quick-clean/apply",
    response_model=QuickCleanResult,
    summary="Apply previewed fixes",
    responses={**SESSION_ERRORS, **VALIDATION_ERROR,
               409: {"model": ErrorResponse, "description": "preview_token is missing or outdated."}},
)
def apply(body: QuickCleanRequest, session: SessionDep) -> dict:
    """Each fix is recorded as its own step, so any of them can be undone."""
    return workspace.apply_quick_clean(session, body.operations, body.preview_token)


@router.get("/report", response_model=ChangeReport, summary="What was changed, for the client", responses=SESSION_ERRORS)
def report(session: SessionDep) -> dict:
    return workspace.change_report(session)


@router.get("/recipe", response_model=Recipe, summary="Applied steps as a reusable recipe",
            responses={**SESSION_ERRORS, 409: {"model": ErrorResponse, "description": "No steps applied yet."}})
def recipe(session: SessionDep) -> dict:
    """Download this, then send its `steps` as `operations` to /api/quick-clean/preview and /apply
    to repeat the same cleaning on another file."""
    return workspace.recipe(session)
