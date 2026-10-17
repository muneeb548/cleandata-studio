"""Housekeeping for the temporary files used during upload and export."""

import tempfile
import time
from pathlib import Path


def remove_stale_temp_files(max_age_seconds: int = 3600) -> int:
    """Delete our own leftover temp files (e.g. after a crash or an interrupted download)."""
    removed = 0
    now = time.time()
    for pattern in ("cleandata_upload_*", "cleandata_export_*"):
        for path in Path(tempfile.gettempdir()).glob(pattern):
            try:
                if path.is_file() and now - path.stat().st_mtime > max_age_seconds:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
    return removed
