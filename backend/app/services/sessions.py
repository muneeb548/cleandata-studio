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


@dataclass
class AttachedFile:
    """Another file added to the session so it can be combined with the working data.

    It is never cleaned itself and lives in memory only, like the main upload."""

    id: str
    name: str
    size: int
    format: str
    sheet: str | None
    df: pd.DataFrame
    warnings: list[str]
    added_at: float
    bytes: int = 0
    # Removed by the user but still needed to rebuild an applied Combine files step
    # (saved sessions replay their steps). Hidden from the file list.
    removed: bool = False

    def public(self) -> dict:
        return {
            "id": self.id, "name": self.name, "size": self.size, "format": self.format, "sheet": self.sheet,
            "rows": len(self.df), "columns": [str(c) for c in self.df.columns], "warnings": self.warnings,
            "added_at": self.added_at,
        }


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
    # Other files added to combine with this one (append rows / join columns), by id.
    files: dict[str, AttachedFile] = field(default_factory=dict)
    # Writes this session to disk after every change when SAVE_SESSIONS is on (see persistence.py).
    saver: Any = field(default=None, repr=False)

    def save(self) -> None:
        if self.saver is not None:
            self.saver(self)

    @property
    def visible_files(self) -> list["AttachedFile"]:
        return [f for f in self.files.values() if not f.removed]

    @property
    def memory_bytes(self) -> int:
        """Estimated memory held by this session: the original, stored undo snapshots and added files."""
        return (self.original_bytes + sum(h.bytes for h in self.history if h.df is not None)
                + sum(f.bytes for f in self.files.values()))

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
        self.prune(max_snapshots, max_bytes)

    def prune(self, max_snapshots: int, max_bytes: int | None = None) -> None:
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
    def __init__(self, ttl_seconds: int, max_sessions: int, max_total_bytes: int = 0, protect_seconds: int = 0,
                 saved_dir: str | None = None, max_snapshots: int = 20, max_history_bytes: int | None = None):
        # ttl_seconds <= 0: sessions never expire (useful with saved sessions on your own computer).
        self.ttl = ttl_seconds
        self.max_sessions = max_sessions
        # Server-wide memory budget for all sessions (0 = none) and how long after its
        # last request a session is protected from being removed to make room.
        self.max_total_bytes = max_total_bytes
        self.protect_seconds = protect_seconds
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        # Saved sessions (SAVE_SESSIONS): kept on disk, reloaded after a restart.
        self.disk = None
        if saved_dir:
            from app.services.persistence import SessionDisk

            self.disk = SessionDisk(saved_dir)
        self.max_snapshots = max_snapshots
        self.max_history_bytes = max_history_bytes
        self._disk_touched: dict[str, float] = {}

    @staticmethod
    def new_id() -> str:
        return secrets.token_urlsafe(32)

    def _expired(self, last_access: float, now: float | None = None) -> bool:
        return self.ttl > 0 and (now or time.time()) - last_access > self.ttl

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
        if self.disk is not None:
            session.saver = self.disk.save
            session.save()
        return session, f"{session.id}.{secret}"

    def total_bytes(self) -> int:
        return sum(s.memory_bytes for s in list(self._sessions.values()))

    def reserve(self, session: Session, extra: int) -> None:
        """Make room in the server-wide memory budget for `extra` bytes that `session` is about
        to hold (an added file). Never removes `session` itself; refuses when there is no room."""
        if not self.max_total_bytes:
            return
        with self._lock:
            self._make_room(session.memory_bytes + extra, exclude=session.id, count_new=False)

    def _make_room(self, needed: int, exclude: str | None = None, count_new: bool = True) -> None:
        """Remove least recently used sessions until the new one fits. Sessions used in the
        last `protect_seconds` are never removed; if nothing can be removed, the new upload
        is refused instead of taking someone's data away mid-task. With saved sessions a
        removed session only leaves memory: it stays on disk and is reloaded when opened.
        Caller holds the lock."""
        if self.max_total_bytes and needed > self.max_total_bytes:
            raise AppError("file_too_large_for_server",
                           "This file needs more memory than this server allows for one dataset.",
                           "Try a smaller file, or split it into parts.", status=413)

        def over() -> bool:
            if count_new and len(self._sessions) >= self.max_sessions:
                return True
            others = sum(s.memory_bytes for sid, s in list(self._sessions.items()) if sid != exclude)
            return bool(self.max_total_bytes) and others + needed > self.max_total_bytes

        now = time.time()
        while over():
            removable = [s for s in self._sessions.values()
                         if s.id != exclude and now - s.last_access >= self.protect_seconds]
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

    @staticmethod
    def _split(token: str | None) -> tuple[str, str] | None:
        if not token or not TOKEN_RE.match(token):
            return None
        session_id, secret = token.split(".", 1)
        return session_id, secret

    def _resolve(self, token: str | None) -> Session | None:
        """Validate the token format and secret; return the session or None. Caller holds the lock."""
        parts = self._split(token)
        if parts is None:
            return None
        session = self._sessions.get(parts[0])
        if session is None or not hmac.compare_digest(session.secret_hash, _hash(parts[1])):
            return None
        return session

    def _load(self, token: str | None) -> Session | None:
        """Reopen a saved session from disk (after a restart, or after it left memory)."""
        parts = self._split(token) if self.disk is not None else None
        if parts is None or not self.disk.exists(parts[0]):
            return None
        last = self.disk.last_access(parts[0])
        if last is not None and self._expired(last):
            self.disk.delete(parts[0])
            return None
        try:
            session = self.disk.load(parts[0], self.max_snapshots, self.max_history_bytes)
        except Exception as exc:  # noqa: BLE001 - a damaged folder must not break the app
            import logging

            logging.getLogger("cleandata").warning("could not reopen a saved session: %s", type(exc).__name__)
            return None
        if not hmac.compare_digest(session.secret_hash, _hash(parts[1])):
            return None
        session.saver = self.disk.save
        return session

    def get(self, token: str | None) -> Session:
        if not token:
            raise AppError("no_session", "No active dataset.", "Upload a file to start.", status=401)
        with self._lock:
            session = self._resolve(token)
            if session is not None and self._expired(session.last_access):
                del self._sessions[session.id]
                if self.disk is not None:
                    self.disk.delete(session.id)
                raise self._not_found()
        if session is None:
            loaded = self._load(token)  # outside the lock: replaying steps can take a moment
            if loaded is None:
                raise self._not_found()
            with self._lock:
                session = self._resolve(token)
                if session is None:
                    self._make_room(loaded.memory_bytes)
                    self._sessions[loaded.id] = loaded
                    session = loaded
        session.last_access = time.time()
        if self.disk is not None and session.last_access - self._disk_touched.get(session.id, 0) > 60:
            self._disk_touched[session.id] = session.last_access
            self.disk.touch(session)
        return session

    def delete(self, token: str | None) -> bool:
        with self._lock:
            session = self._resolve(token)
            parts = self._split(token)
            on_disk = (self.disk is not None and parts is not None and self.disk.exists(parts[0])
                       and (session is not None or self._disk_secret_ok(parts)))
            if session is None and not on_disk:
                return False
            if session is not None:
                del self._sessions[session.id]
            if on_disk:
                self.disk.delete(parts[0])
            return True

    def _disk_secret_ok(self, parts: tuple[str, str]) -> bool:
        import json

        try:
            meta = json.loads((self.disk.root / parts[0] / "meta.json").read_text(encoding="utf-8"))
            return hmac.compare_digest(bytes.fromhex(meta["secret_hash"]), _hash(parts[1]))
        except (OSError, ValueError, KeyError):
            return False

    def cleanup(self) -> int:
        if self.ttl <= 0:
            return 0
        now = time.time()
        with self._lock:
            expired = [sid for sid, s in self._sessions.items() if self._expired(s.last_access, now)]
            for sid in expired:
                del self._sessions[sid]
        if self.disk is not None:
            for sid in set(self.disk.ids()) - set(self._sessions):
                last = self.disk.last_access(sid)
                if last is not None and self._expired(last, now):
                    self.disk.delete(sid)
                    expired.append(sid)
        return len(set(expired))

    def __len__(self) -> int:
        return len(self._sessions)


def new_entry_id() -> str:
    return uuid.uuid4().hex[:12]


store = SessionStore(
    ttl_seconds=settings.session_ttl_minutes * 60,
    max_sessions=settings.max_sessions,
    max_total_bytes=settings.max_total_memory_bytes,
    protect_seconds=settings.session_protect_seconds,
    saved_dir=settings.sessions_dir if settings.save_sessions else None,
    max_snapshots=settings.max_history_snapshots,
    max_history_bytes=settings.max_history_bytes,
)
