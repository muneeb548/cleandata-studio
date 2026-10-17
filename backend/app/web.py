"""Serving the built frontend (frontend/dist) from the API server.

Optional: enabled by setting FRONTEND_DIST. Serving the website and the API from
one origin means no CORS configuration, one HTTPS certificate and one service to
deploy. Only Starlette is used here, so this module can be tested without FastAPI.
"""

from __future__ import annotations

from pathlib import Path

from starlette.responses import FileResponse, JSONResponse, Response

from app.core.security import HTML_CSP

# Pages the single-page app knows (keep in sync with ROUTES in frontend/src/App.tsx).
# Any other path still gets the app (which shows its "page not found" view) but with
# HTTP status 404, so search engines don't index non-existent pages.
SPA_ROUTES = {"", "app", "about", "privacy", "contact"}


class FrontendFiles:
    def __init__(self, dist: str | Path) -> None:
        self.root = Path(dist).resolve()
        self.index = self.root / "index.html"

    @property
    def available(self) -> bool:
        return self.index.is_file()

    def _file(self, path: str) -> Path | None:
        """Resolve a URL path to a file inside the dist folder (never outside it)."""
        if not path or "\x00" in path:
            return None
        try:
            target = (self.root / path).resolve()
        except (OSError, ValueError):
            return None
        if not target.is_relative_to(self.root) or not target.is_file():
            return None
        return target

    def _html(self, status: int = 200) -> Response:
        return FileResponse(
            self.index,
            status_code=status,
            media_type="text/html",
            headers={"Cache-Control": "no-cache", "Content-Security-Policy": HTML_CSP},
        )

    def response(self, path: str) -> Response:
        path = path.strip("/")
        if path == "api" or path.startswith("api/"):
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "not_found", "message": "This API endpoint does not exist.", "hint": None}},
            )
        target = self._file(path)
        if target is not None and target != self.index:
            if path.startswith("assets/"):
                cache = "public, max-age=31536000, immutable"  # file names contain a content hash
            else:
                cache = "public, max-age=3600"
            headers = {"Cache-Control": cache}
            if target.suffix == ".html":
                headers["Content-Security-Policy"] = HTML_CSP
            return FileResponse(target, headers=headers)
        if path in SPA_ROUTES or path == "index.html":
            return self._html()
        # Missing static files (e.g. an old /assets/… after a redeploy) get a plain 404,
        # everything else gets the app's own "page not found" view.
        if path.startswith("assets/"):
            return Response("Not found", status_code=404, media_type="text/plain")
        return self._html(status=404)
