"""Saved sessions (SAVE_SESSIONS=true): keep a dataset on this computer's disk between visits.

Meant for running CleanData Studio on your own computer. With it on, closing the browser,
restarting the server or switching off the laptop no longer loses your work: when you open
the app again you get the same file, the same added files and the same cleaning steps.

What is written, in SESSIONS_DIR/<session id>/:
* original.pkl         the uploaded data, exactly as imported (never changed)
* files/<file id>.pkl  other files added for Combine files
* meta.json            file details, the applied steps (only their settings), the activity
                       log and a hash of the session secret (never the secret itself)

The working data is not stored: on load, the saved steps are replayed on the original.
Every operation is a pure function, so this gives exactly the same result and keeps the
folder small. Files are written by this app only and read back by it only; delete a folder
(or use "Delete my data now") to remove a dataset for good.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

import pandas as pd

from app.services.memory import frame_bytes, new_bytes

log = logging.getLogger("cleandata")

META = "meta.json"
ORIGINAL = "original.pkl"
FORMAT_VERSION = 1


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _write_frame(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=path.parent)
    os.close(fd)
    try:
        df.to_pickle(tmp)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


class SessionDisk:
    """Reads and writes saved sessions in one folder."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _dir(self, session_id: str) -> Path:
        # Session ids are random url-safe tokens (letters, digits, - and _), never user input
        # that reached here unchecked (the token format is validated first).
        return self.root / session_id

    def exists(self, session_id: str) -> bool:
        return (self._dir(session_id) / META).is_file()

    def ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return [p.name for p in self.root.iterdir() if (p / META).is_file()]

    def delete(self, session_id: str) -> None:
        shutil.rmtree(self._dir(session_id), ignore_errors=True)

    # ------------------------------------------------------------------ write

    def save(self, session) -> None:
        """Write everything that changed. Called after every change; cheap after the first time."""
        folder = self._dir(session.id)
        try:
            if not (folder / ORIGINAL).is_file():
                _write_frame(folder / ORIGINAL, session.original)
            for f in session.files.values():
                path = folder / "files" / f"{f.id}.pkl"
                if not path.is_file():
                    _write_frame(path, f.df)
            files_dir = folder / "files"
            if files_dir.is_dir():  # files the user removed and no step needs any more
                for path in files_dir.glob("*.pkl"):
                    if path.stem not in session.files:
                        path.unlink(missing_ok=True)
            meta = {
                "version": FORMAT_VERSION,
                "id": session.id,
                "secret_hash": session.secret_hash.hex(),
                "preview_key": session.preview_key.hex(),
                "filename": session.filename,
                "file_size": session.file_size,
                "encoding": session.encoding,
                "delimiter": session.delimiter,
                "import_warnings": session.import_warnings,
                "format": session.format,
                "sheet": session.sheet,
                "sheets": session.sheets,
                "created_at": session.created_at,
                "last_access": session.last_access,
                "ai_calls": session.ai_calls,
                "files": [{"id": f.id, "name": f.name, "size": f.size, "format": f.format, "sheet": f.sheet,
                           "warnings": f.warnings, "added_at": f.added_at, "removed": f.removed}
                          for f in session.files.values()],
                "history": [{k: v for k, v in h.__dict__.items() if k not in ("df", "bytes")} for h in session.history],
                "log": [e.public() for e in session.log],
                "reviewed": session.reviewed,
            }
            _write_atomic(folder / META, json.dumps(meta, default=str).encode("utf-8"))
        except OSError as exc:
            # Saving is a convenience: the session keeps working in memory.
            log.warning("could not save session to disk: %s", type(exc).__name__)

    def touch(self, session) -> None:
        """Record the time of the last visit (used for SESSION_TTL_MINUTES)."""
        path = self._dir(session.id) / META
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
            meta["last_access"] = session.last_access
            _write_atomic(path, json.dumps(meta, default=str).encode("utf-8"))
        except (OSError, ValueError):
            pass

    def last_access(self, session_id: str) -> float | None:
        try:
            return float(json.loads((self._dir(session_id) / META).read_text(encoding="utf-8"))["last_access"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    # ------------------------------------------------------------------ read

    def load(self, session_id: str, max_snapshots: int, max_bytes: int | None):
        """Rebuild a saved session: read the original and added files, then replay the steps."""
        from pydantic import TypeAdapter

        from app.schemas.operations import Operation
        from app.services.sessions import AttachedFile, HistoryEntry, LogEvent, Session

        folder = self._dir(session_id)
        meta = json.loads((folder / META).read_text(encoding="utf-8"))
        original = pd.read_pickle(folder / ORIGINAL)
        session = Session(
            id=meta["id"], filename=meta["filename"], file_size=meta["file_size"], encoding=meta["encoding"],
            delimiter=meta["delimiter"], import_warnings=list(meta.get("import_warnings") or []), original=original,
            format=meta.get("format", "csv"), sheet=meta.get("sheet"), sheets=list(meta.get("sheets") or []),
            secret_hash=bytes.fromhex(meta["secret_hash"]), preview_key=bytes.fromhex(meta["preview_key"]),
            created_at=meta.get("created_at", time.time()), last_access=meta.get("last_access", time.time()),
            ai_calls=int(meta.get("ai_calls", 0)),
        )
        session.original_bytes = frame_bytes(original)
        for f in meta.get("files", []):
            path = folder / "files" / f"{f['id']}.pkl"
            if not path.is_file():
                continue
            df = pd.read_pickle(path)
            session.files[f["id"]] = AttachedFile(
                id=f["id"], name=f["name"], size=f["size"], format=f["format"], sheet=f.get("sheet"), df=df,
                warnings=list(f.get("warnings") or []), added_at=f["added_at"], bytes=frame_bytes(df),
                removed=bool(f.get("removed")))
        session.log = [LogEvent(**e) for e in meta.get("log", [])]
        session.reviewed = dict(meta.get("reviewed") or {})
        self._replay(session, meta.get("history", []), TypeAdapter(Operation), HistoryEntry, LogEvent)
        session.prune(max_snapshots, max_bytes)
        return session

    @staticmethod
    def _replay(session, steps: list[dict], adapter, HistoryEntry, LogEvent) -> None:
        from app.services.operations import run_operation
        from app.services.workspace import _context

        for i, step in enumerate(steps):
            before = session.current
            try:
                op = adapter.validate_python(step["params"])
                result = run_operation(before, op, _context(session))
                if result.blocked:
                    raise ValueError(result.blocked)
            except Exception as exc:  # noqa: BLE001 - a step that no longer applies ends the replay
                left = len(steps) - i
                log.warning("saved session: step %d could not be repeated (%s); %d step(s) dropped",
                            i + 1, type(exc).__name__, left)
                session.log.append(LogEvent(
                    "reset", time.time(),
                    summary=f"When the saved work was reopened, {left} step(s) from \"{step.get('label', '?')}\" "
                            "on could not be repeated and were removed."))
                break
            entry = HistoryEntry(**{**step, "df": result.df, "bytes": new_bytes(result.df, before)})
            session.history.append(entry)
