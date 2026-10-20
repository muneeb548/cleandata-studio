"""Application settings.

Values come from environment variables (optionally loaded from a local `.env`
file). Every setting has a safe default so the app runs with zero configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines) so we don't need an extra dependency.

    Existing environment variables always win over values in the file.
    """
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(Path(__file__).resolve().parents[2] / ".env")  # backend/.env


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
_PRODUCTION = _ENVIRONMENT == "production"


@dataclass(frozen=True)
class Settings:
    # "development" (default) or "production". Production turns off the
    # interactive API docs, turns on HSTS and checks the configuration at startup.
    environment: str = _ENVIRONMENT
    max_upload_mb: int = field(default_factory=lambda: _int("MAX_UPLOAD_MB", 100))
    session_ttl_minutes: int = field(default_factory=lambda: _int("SESSION_TTL_MINUTES", 30))
    max_sessions: int = field(default_factory=lambda: _int("MAX_SESSIONS", 10))
    max_history_snapshots: int = field(default_factory=lambda: _int("MAX_HISTORY_SNAPSHOTS", 20))
    # Memory budget for older undo steps. The original upload, the current data
    # and the previous step (needed for one undo) are always kept.
    max_history_memory_mb: int = field(default_factory=lambda: _int("MAX_HISTORY_MEMORY_MB", 1024))
    max_page_size: int = field(default_factory=lambda: _int("MAX_PAGE_SIZE", 200))
    rate_limit_per_minute: int = field(default_factory=lambda: _int("RATE_LIMIT_PER_MINUTE", 240))
    upload_limit_per_minute: int = field(default_factory=lambda: _int("UPLOAD_LIMIT_PER_MINUTE", 20))
    cors_origins: list[str] = field(
        # Production default is empty: when the API also serves the website (FRONTEND_DIST),
        # browser requests are same-origin and need no CORS at all.
        default_factory=lambda: _list("CORS_ORIGINS", "" if _PRODUCTION else "http://localhost:5173,http://127.0.0.1:5173")
    )
    # --- Production / capacity settings (all optional) ---
    enable_api_docs: bool = field(default_factory=lambda: _bool("ENABLE_API_DOCS", not _PRODUCTION))
    # Send Strict-Transport-Security (only meaningful when the site is served over HTTPS).
    hsts_seconds: int = field(default_factory=lambda: _int("HSTS_SECONDS", 31536000 if _PRODUCTION else 0))
    # Redirect plain-HTTP requests to HTTPS, using the X-Forwarded-Proto header set by the hosting proxy.
    force_https: bool = field(default_factory=lambda: _bool("FORCE_HTTPS", False))
    # Header the hosting proxy uses for the visitor's IP (e.g. X-Real-IP). Empty = use the
    # direct connection address. Only set this when the app is reachable ONLY through that proxy.
    client_ip_header: str = field(default_factory=lambda: os.getenv("CLIENT_IP_HEADER", "").strip())
    # Total memory budget (MB) for all sessions together. 0 = no global limit (local use).
    max_total_memory_mb: int = field(default_factory=lambda: _int("MAX_TOTAL_MEMORY_MB", 0))
    # A session counts as "in use" for this many seconds after its last request and is then
    # not removed to make room for a new upload; the new upload is refused instead (503).
    # 0 = always remove the least recently used session (local default).
    session_protect_seconds: int = field(default_factory=lambda: _int("SESSION_PROTECT_SECONDS", 0))
    # Uploads processed at the same time. 0 = unlimited. Imports use a lot of memory briefly.
    max_concurrent_uploads: int = field(default_factory=lambda: _int("MAX_CONCURRENT_UPLOADS", 0))
    # Folder with the built frontend (frontend/dist). When set, the API server also serves the website.
    frontend_dist: str = field(default_factory=lambda: os.getenv("FRONTEND_DIST", "").strip())
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO")
    # --- AI assistant (optional, off by default) ---
    # off: no AI. ollama: a model running on this computer (free, data stays here).
    # anthropic: Claude API in the cloud (paid; the user must agree before data is sent).
    ai_provider: str = field(default_factory=lambda: os.getenv("AI_PROVIDER", "off").strip().lower() or "off")
    # Empty = a sensible default for the provider (see app.services.ai_client).
    ai_model: str = field(default_factory=lambda: os.getenv("AI_MODEL", "").strip())
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434").strip().rstrip("/"))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "").strip(), repr=False)
    # Also send up to AI_MAX_VALUES example values per column (needed for value mapping).
    # false = only column names, types and counts ever leave the data.
    ai_send_values: bool = field(default_factory=lambda: _bool("AI_SEND_VALUES", True))
    ai_max_values: int = field(default_factory=lambda: _int("AI_MAX_VALUES", 20))
    ai_timeout_seconds: int = field(default_factory=lambda: _int("AI_TIMEOUT_SECONDS", 180))
    # AI requests allowed per uploaded file (protects a paid API key). 0 = unlimited.
    ai_max_calls_per_session: int = field(default_factory=lambda: _int("AI_MAX_CALLS_PER_SESSION", 30))

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def max_total_memory_bytes(self) -> int:
        return self.max_total_memory_mb * 1024 * 1024

    def problems(self) -> list[str]:
        """Configuration mistakes that are dangerous in production (empty list = fine)."""
        issues = []
        if self.environment not in ("development", "production"):
            issues.append(f"ENVIRONMENT must be 'development' or 'production', not '{self.environment}'.")
        if self.ai_provider not in ("off", "ollama", "anthropic"):
            issues.append(f"AI_PROVIDER must be off, ollama or anthropic, not '{self.ai_provider}'.")
        if self.ai_provider == "anthropic" and not self.anthropic_api_key:
            issues.append("AI_PROVIDER=anthropic needs ANTHROPIC_API_KEY.")
        if self.is_production:
            if any(o == "*" for o in self.cors_origins):
                issues.append("CORS_ORIGINS must list your site's origin(s); '*' is not allowed in production.")
            local = ("http://localhost", "http://127.0.0.1")  # harmless; allows a local production test
            bad = [o for o in self.cors_origins if o != "*" and not o.startswith("https://") and not o.startswith(local)]
            if bad:
                issues.append(f"CORS_ORIGINS should only contain https:// origins in production: {', '.join(bad)}")
            if self.max_upload_mb <= 0:
                issues.append("MAX_UPLOAD_MB must be greater than 0.")
        return issues

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_history_bytes(self) -> int:
        return self.max_history_memory_mb * 1024 * 1024


settings = Settings()
