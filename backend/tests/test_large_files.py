"""Real large-file tests (opt-in, they take ~1 minute and ~1.5 GB of RAM).

Run with:   set CLEANDATA_LARGE_TESTS=1   (PowerShell: $env:CLEANDATA_LARGE_TESTS=1)
            pytest tests/test_large_files.py -s
"""

import csv
import json
import os
import random
import time

import pytest

from tests.conftest import preview_apply
from app.core.config import settings
from app.core.errors import AppError
from app.services import workspace as ws
from app.services.operations import RemoveDuplicates, StandardizeText, TrimWhitespace

pytestmark = pytest.mark.skipif(os.getenv("CLEANDATA_LARGE_TESTS") != "1", reason="set CLEANDATA_LARGE_TESTS=1 to run")

MB = 1024 * 1024


def make_csv(path, target_bytes):
    rng = random.Random(1)
    cities = ["Lahore", "lahore", " Karachi ", "Islamabad", ""]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "city", "amount", "note"])
        i = 0
        while f.tell() < target_bytes - 200:
            i += 1
            w.writerow([i, f"Customer {rng.randint(1, 10**6)}", rng.choice(cities),
                        "" if rng.random() < 0.03 else f"{rng.gauss(4500, 900):.2f}",
                        rng.choice(["", "VIP, call", 'said "hi"', "two\nlines"])])
    return os.path.getsize(path)


def timed(label, fn):
    t = time.perf_counter()
    out = fn()
    print(f"{label}: {time.perf_counter() - t:.1f}s")
    return out


def test_real_csv_just_under_100_mb(tmp_path, fresh_store):
    path = str(tmp_path / "big.csv")
    size = make_csv(path, settings.max_upload_bytes - MB)
    assert 98 * MB < size <= settings.max_upload_bytes
    info = timed("import", lambda: ws.create_session_from_path(fresh_store, "big.csv", path, size))
    s = fresh_store.get(info["session_id"])
    rows = info["current_shape"]["rows"]
    assert rows > 1_000_000
    timed("profile", lambda: ws.get_profile(s))
    timed("dedupe", lambda: preview_apply(s, RemoveDuplicates(type="remove_duplicates")))
    timed("trim", lambda: preview_apply(s, TrimWhitespace(type="trim_whitespace")))
    timed("title", lambda: preview_apply(s, StandardizeText(type="standardize_text", columns=["city"], case="title")))
    timed("undo", lambda: ws.undo(s))
    timed("reset", lambda: ws.reset(s))
    out, _, _ = timed("export csv", lambda: ws.export_file(s, None, "csv"))
    # Round trip: the export must contain every row (nothing silently dropped).
    with open(out, newline="", encoding="utf-8") as f:
        assert sum(1 for _ in csv.reader(f)) - 1 == rows
    os.remove(out)


def test_real_csv_over_100_mb_is_rejected(tmp_path, fresh_store):
    path = str(tmp_path / "too_big.csv")
    size = make_csv(path, settings.max_upload_bytes + 2 * MB)
    assert size > settings.max_upload_bytes
    with pytest.raises(AppError) as exc:
        ws.create_session_from_path(fresh_store, "too_big.csv", path, size)
    assert exc.value.status == 413


def test_real_json_lines_large(tmp_path, fresh_store):
    path = tmp_path / "big.json"
    with open(path, "w", encoding="utf-8") as f:
        i = 0
        while f.tell() < 60 * MB:
            i += 1
            f.write(json.dumps({"id": i, "name": f"n{i}", "nested": {"a": i % 7, "b": [1, 2]}}) + "\n")
    info = timed("json import", lambda: ws.create_session_from_path(fresh_store, "big.json", str(path), path.stat().st_size))
    assert info["current_shape"]["rows"] == i
