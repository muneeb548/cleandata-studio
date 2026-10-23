"""Mark detected issues as reviewed (checked and left as they are), or undo that."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SESSION_ERRORS, SessionDep
from app.schemas.responses import ErrorResponse, ReviewedList, ReviewRequest
from app.services import workspace

router = APIRouter(prefix="/issues", tags=["dataset"])


@router.post("/review", response_model=ReviewedList, summary="Mark an issue as reviewed",
             responses={**SESSION_ERRORS, 422: {"model": ErrorResponse, "description": "No reason given."}})
def review(body: ReviewRequest, session: SessionDep) -> dict:
    """The issue leaves the open list and is listed, with the reason, in the change report
    under "Checked and left as they are". Nothing in the data changes."""
    return workspace.review_issue(session, body.issue_id, body.reason)


@router.post("/unreview", response_model=ReviewedList, summary="Undo Mark as reviewed", responses=SESSION_ERRORS)
def unreview(body: ReviewRequest, session: SessionDep) -> dict:
    return workspace.unreview_issue(session, body.issue_id)
