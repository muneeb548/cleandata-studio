"""In-memory session store.

Lifecycle rules (documented in README):
* Each upload creates a session and returns a token "<id>.<secret>": two
  independent 256-bit random values. Only a SHA-256 hash of the secret is
  stored, and it is compared in constant time, so a session cannot be opened
  by guessing, by a timing attack on the lookup, or by someone who only learns
  the public id (for example from a log line).
* Data lives only in this process's memory. Nothing is written to disk.
* A session expires after SESSION_TTL_MINUTES without activity, or when the
  user starts over. Restarting the server clears every session.
* The original DataFrame is stored once and never modified. Each applied
  operation pushes a new snapshot; the newest snapshot is the working dataset.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.core.config import settings
from app.core.errors import AppError
from app.services.memory import frame_bytes


@dataclass
class HistoryEntry:
    id: str
    type: str
    label: str
    params: dict[str, Any]
    summary: str
    applied_at: float
    rows_before: int
    rows_after: int
    columns_before: int
    columns_after: int
    rows_removed: int
    columns_removed: int
    cells_changed: int
    warnings: list[str]
    df: pd.DataFrame | None  # snapshot after this step (None once pruned to save memory)
    bytes: int = 0  # estimated memory this snapshot adds on top of the previous one

    def public(self) -> dict:
        data = {k: v for k, v in self.__dict__.items() if k not in ("df", "bytes")}
        data["undoable"] = self.df is not None
        return data


TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}\.[A-Za-z0-9_-]{43}$")


def _hash(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("ascii")).digest()


@dataclass
class LogEvent:
    """One line of the audit trail: applied, undone or reset."""

    event: str
    at: float
    step_id: str | None = None
    type: str | None = None
    label: str | None = None
    summary: str | None = None

    def public(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Session:
    id: str
    filename: str
    file_size: int
    encoding: str
    delimiter: str
    import_warnings: list[str]
    original: pd.DataFrame
    format: str = "csv"
    sheet: str | None = None
    sheets: list[str] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)
    # Full audit trail, including steps that were later undone or reset.
    log: list[LogEvent] = field(default_factory=list)
    secret_hash: bytes = field(default=b"", repr=False)
    preview_key: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    # Results that are expensive on large data (profiles, stats, sorted views),
    # keyed by dataset version so they are never stale.
    cache: dict = field(default_factory=dict, repr=False)
    # Estimated memory of the original upload (for the server-wide memory budget).
    original_bytes: int = 0
    # AI assistant requests made for this file (see AI_MAX_CALLS_PER_SESSION).
    ai_calls: int = 0

    @property
    def memory_bytes(self) -> int:
        """Estimated memory held by this session: the original plus stored undo snapshots."""
        return self.original_bytes + sum(h.bytes for h in self.history if h.df is not None)

    # ------------------------------------------------------------------ previews

    def preview_token(self, op_params: dict) -> str:
        """Bind a preview to the exact operation and dataset version it was computed for."""
        payload = json.dumps([self.version_key, op_params], sort_keys=True, default=str).encode()
        return hmac.new(self.preview_key, payload, hashlib.sha256).hexdigest()[:40]

    def check_preview_token(self, op_params: dict, token: str | None) -> bool:
        return bool(token) and hmac.compare_digest(self.preview_token(op_params), token)

    @property
    def version_key(self) -> str:
        return self.history[-1].id if self.history else "original"

    def cached(self, key: tuple, compute):
        if key in self.cache:
            return self.cache[key]
        value = compute()
        self.cache[key] = value
        while len(self.cache) > 12:
            self.cache.pop(next(iter(self.cache)))
        return value

    @property
    def current(self) -> pd.DataFrame:
        for entry in reversed(self.history):
            if entry.df is not None:
                return entry.df
        return self.original

    @property
    def can_undo(self) -> bool:
        if not self.history:
            return False
        return len(self.history) == 1 or self.history[-2].df is not None

    def push(self, entry: HistoryEntry, max_snapshots: int, max_bytes: int | None = None) -> None:
        """Add a step and drop the oldest undo snapshots beyond the count/memory budget.

        The newest two snapshots are always kept so the last step can be undone.
        Dropped steps stay in the activity log but can no longer be undone.
        """
        self.history.append(entry)
        self.log.append(LogEvent("applied", entry.applied_at, entry.id, entry.type, entry.label, entry.summary))
        keep_always = 2
        while True:
            stored = [h for h in self.history if h.df is not None]
            prunable = stored[:-keep_always]
            if not prunable:
                break
            too_many = len(stored) > max_snapshots
            too_big = max_bytes is not None and sum(h.bytes for h in prunable) > max_bytes
            if not (too_many or too_big):
                break
            prunable[0].df = None

    def undo(self) -> HistoryEntry:
        if not self.can_undo:
            raise AppError("cannot_undo", "There is nothing to undo.",
                           "Undo history is limited; use Reset to return to the original data.", status=409)
        entry = self.history.pop()
        self.log.append(LogEvent("undone", time.time(), entry.id, entry.type, entry.label, entry.summary))
        return entry

    def reset(self) -> int:
        removed = len(self.history)
        self.history.clear()
        self.log.append(LogEvent("reset", time.time(), summary=f"Restored the original upload; {removed} step(s) removed."))
        return removed



class SessionStore:
    def __init__(self, ttl_seconds: int, max_sessions: int, max_total_bytes: int = 0, protect_seconds: int = 0):
        self.ttl = ttl_seconds
        self.max_sessions = max_sessions
        # Server-wide memory budget for all sessions (0 = none) and how long after its
        # last request a session is protected from being removed to make room.
        self.max_total_bytes = max_total_bytes
        self.protect_seconds = protect_seconds
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    @staticmethod
    def new_id() -> str:
        return secrets.token_urlsafe(32)

    def create(self, **kwargs) -> tuple[Session, str]:
        """Create a session and return it with its token. The secret part of the
        token is returned once and never stored (only its hash is)."""
        self.cleanup()
        secret = self.new_id()
        session = Session(id=self.new_id(), secret_hash=_hash(secret), **kwargs)
        if self.max_total_bytes and not session.original_bytes:
            session.original_bytes = frame_bytes(session.original)
        with self._lock:
            self._make_room(session.original_bytes)
            self._sessions[session.id] = session
        return session, f"{session.id}.{secret}"

    def total_bytes(self) -> int:
        return sum(s.memory_bytes for s in list(self._sessions.values()))

    def _make_room(self, needed: int) -> None:
        """Remove least recently used sessions until the new one fits. Sessions used in the
        last `protect_seconds` are never removed; if nothing can be removed, the new upload
        is refused instead of taking someone's data away mid-task. Caller holds the lock."""
        if self.max_total_bytes and needed > self.max_total_bytes:
            raise AppError("file_too_large_for_server",
                           "This file needs more memory than this server allows for one dataset.",
                           "Try a smaller file, or split it into parts.", status=413)

        def over() -> bool:
            if len(self._sessions) >= self.max_sessions:
                return True
            return bool(self.max_total_bytes) and self.total_bytes() + needed > self.max_total_bytes

        now = time.time()
        while over():
            removable = [s for s in self._sessions.values() if now - s.last_access >= self.protect_seconds]
            if not removable:
                raise AppError("server_busy", "The server is busy with other people's datasets right now.",
                               "Please try again in a few minutes, or try a smaller file.", status=503)
            oldest = min(removable, key=lambda s: s.last_access)
            del self._sessions[oldest.id]

    @staticmethod
    def _not_found() -> AppError:
        return AppError("session_expired", "Your session has expired or does not exist.",
                        "For privacy, data is deleted after a period of inactivity. Upload the file again.",
                        status=404)

    def _resolve(self, token: str | None) -> Session | None:
        """Validate the token format and secret; return the session or None. Caller holds the lock."""
        if not token or not TOKEN_RE.match(token):
            return None
        session_id, secret = token.split(".", 1)
        session = self._sessions.get(session_id)
        if session is None or not hmac.compare_digest(session.secret_hash, _hash(secret)):
            return None
        return session

    def get(self, token: str | None) -> Session:
        if not token:
            raise AppError("no_session", "No active dataset.", "Upload a file to start.", status=401)
        with self._lock:
            session = self._resolve(token)
            if session is not None and time.time() - session.last_access > self.ttl:
                del self._sessions[session.id]
                session = None
            if session is None:
                raise self._not_found()
            session.last_access = time.time()
            return session

    def delete(self, token: str | None) -> bool:
        with self._lock:
            session = self._resolve(token)
            if session is None:
                return False
            del self._sessions[session.id]
            return True

    def cleanup(self) -> int:
        now = time.time()
        with self._lock:
            expired = [sid for sid, s in self._sessions.items() if now - s.last_access > self.ttl]
            for sid in expired:
                del self._sessions[sid]
        return len(expired)

    def __len__(self) -> int:
        return len(self._sessions)


def new_entry_id() -> str:
    return uuid.uuid4().hex[:12]


store = SessionStore(
    ttl_seconds=settings.session_ttl_minutes * 60,
    max_sessions=settings.max_sessions,
    max_total_bytes=settings.max_total_memory_bytes,
    protect_seconds=settings.session_protect_seconds,
)
