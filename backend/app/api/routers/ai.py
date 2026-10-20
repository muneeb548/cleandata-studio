"""AI assistant (optional). Off unless AI_PROVIDER is set in backend/.env."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.deps import SESSION_ERRORS, SessionDep
from app.schemas.responses import AiAnswer, AiMappings, AiPlan, AiStatus, AiSummary, ErrorResponse
from app.services import ai

router = APIRouter(prefix="/ai", tags=["ai assistant"])

AI_ERRORS = {
    **SESSION_ERRORS,
    400: {"model": ErrorResponse, "description": "Consent is missing, or the request is not possible with the current settings."},
    429: {"model": ErrorResponse, "description": "The AI request limit for this file was reached."},
    502: {"model": ErrorResponse, "description": "The AI answered with something unusable."},
    503: {"model": ErrorResponse, "description": "The AI is turned off, not running, or unreachable."},
}


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consent: bool = Field(False, description="Required (true) when the AI runs in the cloud.")


class PlanRequest(_Body):
    request: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]


class MappingRequest(_Body):
    column: Annotated[str, StringConstraints(min_length=1, max_length=1000)]


class AskRequest(_Body):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]


class SummaryRequest(_Body):
    language: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=40)] = "English"


@router.get("/status", response_model=AiStatus, summary="Is the AI assistant available?")
def status() -> dict:
    return ai.status()


@router.post("/plan", response_model=AiPlan, summary="Turn a plain-language request into cleaning steps", responses=AI_ERRORS)
def plan(body: PlanRequest, session: SessionDep) -> dict:
    """Nothing is changed. Preview and apply the returned steps with /api/quick-clean/preview and /apply."""
    return ai.plan(session, body.request, body.consent)


@router.post("/map-values", response_model=AiMappings, summary="Suggest how to unify a column's values", responses=AI_ERRORS)
def map_values(body: MappingRequest, session: SessionDep) -> dict:
    """Suggestions only: use them in a map_values operation, which is previewed before it is applied."""
    return ai.suggest_mappings(session, body.column, body.consent)


@router.post("/summary", response_model=AiSummary, summary="Plain-language report of the cleaning", responses=AI_ERRORS)
def summary(body: SummaryRequest, session: SessionDep) -> dict:
    return ai.summary(session, body.language, body.consent)


@router.post("/ask", response_model=AiAnswer, summary="Answer a question about the data", responses={
    **AI_ERRORS, 422: {"model": ErrorResponse, "description": "The AI's query plan could not be used."}})
def ask(body: AskRequest, session: SessionDep) -> dict:
    """The AI writes a small query plan (filters, grouping, calculation); the app checks it and computes
    the answer with pandas, so every number comes from the data. Nothing is changed."""
    return ai.ask(session, body.question, body.consent)
