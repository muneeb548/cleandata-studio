"""Before-and-after comparison."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import SESSION_ERRORS, SessionDep
from app.schemas.responses import CompareResponse, CompareRowsPage
from app.services import workspace

router = APIRouter(prefix="/compare", tags=["compare"])


@router.get("", response_model=CompareResponse, summary="Original vs current statistics", responses=SESSION_ERRORS)
def compare(session: SessionDep) -> dict:
    return workspace.compare(session)


@router.get("/rows", response_model=CompareRowsPage, summary="Row-level comparison", responses=SESSION_ERRORS)
def compare_rows(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=1000)] = 50,
    changes_only: bool = False,
) -> dict:
    """Original and current rows aligned by their row number in the upload; changed cells flagged."""
    return workspace.compare_rows(session, page, page_size, changes_only)
