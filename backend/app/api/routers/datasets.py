"""Read-only views of the dataset: quality profile, paginated rows, outliers."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import SESSION_ERRORS, VALIDATION_ERROR, SessionDep
from app.schemas.responses import ColumnValues, OutlierReport, Profile, RowsPage
from app.services import workspace

router = APIRouter(tags=["dataset"])

Dataset = Literal["original", "current"]


@router.get("/profile", response_model=Profile, summary="Data quality profile", responses=SESSION_ERRORS)
def profile(
    session: SessionDep,
    dataset: Dataset = "current",
    light: Annotated[bool, Query(description="Only types and missing counts (fast, for forms).")] = False,
) -> dict:
    """Statistics, per-column profile, type distribution and detected issues,
    all calculated from the selected dataset (`current` working data or the `original` upload)."""
    return workspace.get_profile(session, dataset, light)


@router.get("/rows", response_model=RowsPage, summary="Paginated rows", responses={**SESSION_ERRORS, **VALIDATION_ERROR})
def rows(
    session: SessionDep,
    dataset: Dataset = "current",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=1000, description="Capped at MAX_PAGE_SIZE.")] = 100,
    search: Annotated[str | None, Query(max_length=200, description="Case-insensitive text search across all columns.")] = None,
    sort_by: Annotated[str | None, Query(max_length=1000)] = None,
    sort_dir: Literal["asc", "desc"] = "asc",
) -> dict:
    return workspace.get_rows(session, dataset, page, page_size, search, sort_by, sort_dir)


@router.get("/outliers", response_model=OutlierReport, summary="IQR outlier report (read-only)", responses={**SESSION_ERRORS, **VALIDATION_ERROR})
def outliers(session: SessionDep, column: Annotated[str, Query(max_length=1000)]) -> dict:
    """Values below Q1 − 1.5·IQR or above Q3 + 1.5·IQR. Never modifies the data."""
    return workspace.get_outliers(session, column)


@router.get("/values", response_model=ColumnValues, summary="Different values of one column", responses={**SESSION_ERRORS, **VALIDATION_ERROR})
def values(
    session: SessionDep,
    column: Annotated[str, Query(max_length=1000)],
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> dict:
    """Each different value of the column with its count, most frequent first. Used to build value mappings."""
    return workspace.get_values(session, column, limit)
