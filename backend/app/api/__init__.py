"""HTTP layer: thin routers that validate input and call app.services."""

from fastapi import APIRouter

from app.api.routers import compare, datasets, export, history, operations, sessions, system

api_router = APIRouter(prefix="/api")
for module in (system, sessions, datasets, operations, history, compare, export):
    api_router.include_router(module.router)
