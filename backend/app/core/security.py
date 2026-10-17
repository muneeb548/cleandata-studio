"""Small, dependency-free security helpers: response headers and a per-IP rate limiter."""

from __future__ import annotations

import ipaddress
import threading
import time
from collections import defaultdict, deque

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
}

# Policy for the website's HTML pages when the API server also serves the frontend.
# Scripts, fonts and images all come from the same origin (Vite bundles them);
# 'unsafe-inline' for styles is needed for style attributes set by React/Recharts.
HTML_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def response_headers(*, hsts_seconds: int = 0, is_docs: bool = False) -> dict[str, str]:
    """Security headers for a response. The API docs page loads its own scripts,
    so it gets no Content-Security-Policy."""
    headers = dict(SECURITY_HEADERS)
    if is_docs:
        headers.pop("Content-Security-Policy")
    if hsts_seconds > 0:
        headers["Strict-Transport-Security"] = f"max-age={hsts_seconds}"
    return headers


def client_ip(peer: str | None, headers, header_name: str = "") -> str:
    """The visitor's IP address, used only as the rate-limit key.

    By default the direct connection address is used. Behind a hosting proxy,
    every request comes from the proxy, so `header_name` (e.g. X-Real-IP) can be
    configured. For X-Forwarded-For the right-most entry is used, because that is
    the one the nearest proxy added; entries further left can be forged by the
    client. Invalid values fall back to the connection address.
    """
    fallback = peer or "unknown"
    if not header_name:
        return fallback
    raw = headers.get(header_name) or headers.get(header_name.lower())
    if not raw:
        return fallback
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return fallback
    candidate = parts[-1] if header_name.lower() == "x-forwarded-for" else parts[0]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return fallback


class ConcurrencyGate:
    """Allows at most `limit` operations at once (0 = unlimited). Non-blocking:
    callers that don't get a slot are told to try again later."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._active = 0
        self._lock = threading.Lock()

    def try_enter(self) -> bool:
        with self._lock:
            if self.limit > 0 and self._active >= self.limit:
                return False
            self._active += 1
            return True

    def leave(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)

    @property
    def active(self) -> int:
        return self._active


class RateLimiter:
    """Sliding one-minute window per client key. In-memory, single process."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            if len(self._hits) > 10_000:  # guard against unbounded growth
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True


rate_limiter = RateLimiter()
