"""Health and public configuration."""

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.responses import AppConfig, Health
from app.services import workspace
from app.services.importers import FORMATS

router = APIRouter(tags=["system"])


@router.get("/health", response_model=Health, summary="Health check")
def health() -> dict:
    return {"status": "ok"}


@router.get("/config", response_model=AppConfig, summary="Limits and supported formats")
def config() -> dict:
    return {
        "max_upload_mb": settings.max_upload_mb,
        "session_ttl_minutes": settings.session_ttl_minutes,
        "max_page_size": settings.max_page_size,
        "formats": list(FORMATS),
        "export_formats": list(workspace.EXPORT_FORMATS),
    }
