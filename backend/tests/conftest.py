import os
import sys
from pathlib import Path

os.environ.setdefault("CLEANDATA_STRICT_SCHEMAS", "1")  # response models reject undocumented fields
# The API tests upload many files from one client; rate limiting has its own test.
os.environ.setdefault("UPLOAD_LIMIT_PER_MINUTE", "100000")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "100000")

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.csv_loader import load_csv  # noqa: E402
from app.services.sessions import SessionStore  # noqa: E402

MB = 1024 * 1024


def load(text: str | bytes, max_bytes: int = 10 * MB):
    raw = text.encode("utf-8") if isinstance(text, str) else text
    return load_csv(raw, max_bytes)


@pytest.fixture
def frame():
    """Build a DataFrame exactly the way an upload would."""
    return lambda text: load(text).df


@pytest.fixture
def fresh_store():
    return SessionStore(ttl_seconds=600, max_sessions=10)


MESSY_CSV = (
    "Name ,City,Age,Salary,Joined\n"
    "  Ali ,Lahore,25,50000,2024-01-05\n"
    "Sara,lahore,,62000,2024-02-10\n"
    "Sara,lahore,,62000,2024-02-10\n"
    "Omar,KARACHI,31,,not a date\n"
    "Zoya,Islamabad,29,1000000,2024-03-01\n"
    "Bilal,Lahore,27,51000,2024-03-15\n"
)


def preview_apply(session, op):
    """Preview an operation, then apply it with the preview token (the real client flow)."""
    from app.services import workspace

    token = workspace.preview_operation(session, op)["preview_token"]
    return workspace.apply_operation(session, op, preview_token=token)
