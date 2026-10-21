"""HTTP layer: thin routers that validate input and call app.services."""

from fastapi import APIRouter

from app.api.routers import (ai, compare, datasets, export, files, history, operations, quick_clean, sessions,
                             system)

api_router = APIRouter(prefix="/api")
for module in (system, sessions, files, datasets, operations, quick_clean, history, compare, export, ai):
    api_router.include_router(module.router)
