"""Big file mode: compact text storage (Apache Arrow) and chunked CSV import."""

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

from app.schemas.operations import FindReplace, StandardizeText, TrimWhitespace
from app.services import csv_loader
from app.services.csv_loader import STRING_DTYPE, load_csv
from app.services.memory import frame_bytes, new_bytes
from app.services.operations import run_operation

HAS_ARROW = importlib.util.find_spec("pyarrow") is not None

ROWS = "id,name,city,note\n" + "".join(
    f'{i},"Name {i}",{["Lahore", "", " Karachi "][i % 3]},"a, ""quoted""\nline {i}"\n' for i in range(523)
)


@pytest.mark.skipif(not HAS_ARROW, reason="pyarrow is not installed")
def test_text_uses_arrow_storage_when_available():
    assert STRING_DTYPE.storage == "pyarrow"
    df = load_csv(b"a,b\nx,1\n").df
    assert all(str(t.storage) == "pyarrow" for t in df.dtypes)


@pytest.mark.parametrize("chunk", [1, 7, 100, 10**9])
def test_chunked_import_gives_the_same_data(monkeypatch, chunk):
    whole = load_csv(ROWS.encode()).df
    monkeypatch.setattr(csv_loader, "CSV_CHUNK_ROWS", chunk)
    parts = load_csv(ROWS.encode()).df
    assert parts.shape == (523, 4)
    pd.testing.assert_frame_equal(parts, whole)
    assert list(parts.index) == list(range(523))


@pytest.mark.parametrize("text,shape", [
    ("a,b\n", (0, 2)),
    ("a,b\n\n\n", (0, 2)),
    ("\n\na,b\n1,2\n\n", (1, 2)),
    ("x\n\n1\n\n", (2, 1)),
])
def test_chunked_import_edge_cases(monkeypatch, text, shape):
    monkeypatch.setattr(csv_loader, "CSV_CHUNK_ROWS", 1)
    assert load_csv(text.encode()).df.shape == shape


def test_changed_column_is_the_only_new_memory():
    df = load_csv(ROWS.encode()).df
    after = run_operation(df, StandardizeText(type="standardize_text", columns=["name"], case="upper")).df
    changed = new_bytes(after, df)
    assert 0 < changed < frame_bytes(after)
    assert new_bytes(df, df) == 0


def test_operations_keep_compact_storage():
    df = load_csv(ROWS.encode()).df
    out = run_operation(df, TrimWhitespace(type="trim_whitespace")).df
    out = run_operation(out, FindReplace(type="find_replace", columns=["note"], find="a, \"quoted\"", replace="x(1).*",
                                         match="contains")).df
    assert out["city"].iloc[0] == "Lahore" and pd.isna(out["city"].iloc[1]) and out["city"].iloc[2] == "Karachi"
    assert out["note"].iloc[0] == "x(1).*\nline 0"
    assert str(out["note"].dtype.storage) == STRING_DTYPE.storage


def test_measure_script_makes_a_valid_file(tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts" / "measure_memory.py"
    spec = importlib.util.spec_from_file_location("measure_memory", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["measure_memory"] = module
    spec.loader.exec_module(module)
    target = tmp_path / "big.csv"
    rows = module.make_csv(target, 1)
    df = load_csv(target.read_bytes()).df
    assert df.shape == (rows, 9)
    assert module.peak_memory_mb() > 0
