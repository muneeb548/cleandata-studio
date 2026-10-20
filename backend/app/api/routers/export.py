"""Download the cleaned dataset."""

from __future__ import annotations

import os
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.api.deps import SESSION_ERRORS, SessionDep
from app.schemas.responses import ErrorResponse
from app.services import workspace

router = APIRouter(tags=["export"])


@router.get(
    "/export",
    response_class=FileResponse,
    summary="Download the working data",
    responses={
        **SESSION_ERRORS,
        200: {"content": {"text/csv": {}, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}},
              "description": "The file, as an attachment."},
        422: {"model": ErrorResponse, "description": "Excel limits exceeded (rows, columns, cell length)."},
    },
)
def export(
    session: SessionDep,
    filename: Annotated[str | None, Query(max_length=150, description="Output name without extension; unsafe characters are replaced.")] = None,
    format: Literal["csv", "xlsx"] = "csv",
    bom: Annotated[bool, Query(description="CSV only: add a UTF-8 BOM for Excel.")] = False,
    protect_formulas: Annotated[bool, Query(description="CSV only: prefix text starting with = + - @ with an apostrophe so spreadsheets don't run it.")] = False,
    include_report: Annotated[bool, Query(description="Excel only: add a \"Cleaning report\" sheet describing every change.")] = False,
) -> FileResponse:
    """Generated from the current working data (never the original upload unless nothing was changed)."""
    path, name, media_type = workspace.export_file(session, filename, format, bom, protect_formulas, include_report)
    ascii_name = name.encode("ascii", "ignore").decode() or f"cleaned_data.{format}"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"
    return FileResponse(path, media_type=media_type, headers={"Content-Disposition": disposition},
                        background=BackgroundTask(os.remove, path))
