"""Import/export tests for CSV, TSV, Excel and JSON, plus invalid and corrupted files."""

import io
import json
from datetime import datetime

import pandas as pd
import pytest

from tests.conftest import preview_apply
from app.core.errors import AppError
from app.services import workspace as ws
from app.services.importers import load_file, load_json, validate_filename
from app.services.operations import RemoveDuplicates, StandardizeText, TrimWhitespace

openpyxl = pytest.importorskip("openpyxl")


def write(tmp_path, name, data: bytes | str):
    p = tmp_path / name
    p.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return str(p)


def make_xlsx(tmp_path, name="data.xlsx", sheets=None):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    sheets = sheets or {"Customers": [["ID", "Name", "Joined", "Score", "Active", "Mixed"],
                                      [1, "Ali", datetime(2024, 1, 5), 4.5, True, "a"],
                                      [2, " Sara ", datetime(2024, 2, 1, 13, 30), None, False, 7],
                                      [3, None, None, 3, True, None]]}
    for title, rows in sheets.items():
        sh = wb.create_sheet(title)
        for r in rows:
            sh.append(r)
    p = tmp_path / name
    wb.save(p)
    return str(p)


# ----------------------------------------------------------------- detection & validation

@pytest.mark.parametrize("name", ["a.csv", "a.TSV", "a.xlsx", "a.xls", "a.json", "a.jsonl"])
def test_supported_extensions(name):
    assert validate_filename(name) == name


@pytest.mark.parametrize("name", ["a.pdf", "a.png", "a.docx", "a.zip", "a.exe"])
def test_unsupported_extensions(name):
    with pytest.raises(AppError) as exc:
        validate_filename(name)
    assert exc.value.status == 415


def test_pdf_renamed_to_csv_is_rejected(tmp_path):
    p = write(tmp_path, "fake.csv", b"%PDF-1.7\n...")
    with pytest.raises(AppError) as exc:
        load_file(p, "fake.csv")
    assert exc.value.code == "unsupported_content"


def test_image_renamed_to_json_is_rejected(tmp_path):
    p = write(tmp_path, "fake.json", b"\x89PNG\r\n\x1a\n....")
    with pytest.raises(AppError):
        load_file(p, "fake.json")


# ----------------------------------------------------------------- TSV

def test_tsv_import(tmp_path):
    p = write(tmp_path, "d.tsv", "name\tcity\tnote\nAli\tLahore\thas, comma\nSara\tKarachi\t\n")
    res = load_file(p, "d.tsv")
    assert res.format == "tsv" and res.delimiter == "\t"
    assert res.df.loc[0, "note"] == "has, comma"
    assert pd.isna(res.df.loc[1, "note"])


def test_format_override(tmp_path):
    p = write(tmp_path, "d.csv", "a\tb\n1\t2\n")
    res = load_file(p, "d.csv", requested_format="tsv")
    assert list(res.df.columns) == ["a", "b"]


# ----------------------------------------------------------------- Excel

def test_xlsx_import_keeps_types(tmp_path):
    res = load_file(make_xlsx(tmp_path), "data.xlsx")
    df = res.df
    assert res.format == "xlsx" and res.sheet == "Customers"
    assert list(df.columns) == ["ID", "Name", "Joined", "Score", "Active", "Mixed"]
    assert str(df["ID"].dtype) == "Int64"
    assert str(df["Score"].dtype) == "Float64" and pd.isna(df.loc[1, "Score"])
    assert pd.api.types.is_datetime64_any_dtype(df["Joined"])
    assert df.loc[0, "Joined"] == pd.Timestamp("2024-01-05")
    assert df.loc[0, "Active"] == "TRUE"
    assert df["Mixed"].tolist()[:2] == ["a", "7"]  # mixed column becomes text
    assert df.loc[1, "Name"] == " Sara "  # text kept exactly


def test_xlsx_sheet_selection(tmp_path):
    p = make_xlsx(tmp_path, sheets={"First": [["a"], [1]], "Second": [["b"], ["x"], ["y"]]})
    res = load_file(p, "data.xlsx")
    assert res.sheet == "First" and res.sheets == ["First", "Second"]
    assert any("2 sheets" in w for w in res.warnings)
    res2 = load_file(p, "data.xlsx", sheet="Second")
    assert list(res2.df["b"]) == ["x", "y"]
    with pytest.raises(AppError) as exc:
        load_file(p, "data.xlsx", sheet="Nope")
    assert exc.value.code == "unknown_sheet"


def test_xlsx_empty_sheet(tmp_path):
    p = make_xlsx(tmp_path, sheets={"Empty": []})
    with pytest.raises(AppError) as exc:
        load_file(p, "data.xlsx")
    assert exc.value.code == "empty_file"


def test_corrupted_xlsx(tmp_path):
    p = write(tmp_path, "broken.xlsx", b"PK\x03\x04this is not really a workbook")
    with pytest.raises(AppError) as exc:
        load_file(p, "broken.xlsx")
    assert exc.value.code == "corrupt_file"


def test_text_file_named_xlsx(tmp_path):
    p = write(tmp_path, "fake.xlsx", "a,b\n1,2\n")
    with pytest.raises(AppError) as exc:
        load_file(p, "fake.xlsx")
    assert exc.value.code == "corrupt_file"


def test_corrupted_xls(tmp_path):
    p = write(tmp_path, "broken.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
    with pytest.raises(AppError) as exc:
        load_file(p, "broken.xls")
    assert exc.value.code in ("corrupt_file", "missing_dependency")


def test_xlsx_renamed_to_xls_is_still_read(tmp_path):
    p = make_xlsx(tmp_path, name="renamed.xls")
    assert load_file(p, "renamed.xls").format == "xlsx"


# ----------------------------------------------------------------- JSON

def test_json_array_of_objects(tmp_path):
    data = '[{"id": 1, "price": 2.50, "tags": [1, 2], "meta": {"ok": true}}, {"id": 2, "price": null, "extra": "x"}]'
    res = load_file(write(tmp_path, "d.json", data), "d.json")
    df = res.df
    assert list(df.columns) == ["id", "price", "tags", "meta.ok", "extra"]
    assert df.loc[0, "price"] == "2.50"  # exact original number text
    assert df.loc[0, "tags"] == "[1,2]"
    assert df.loc[0, "meta.ok"] == "true"
    assert pd.isna(df.loc[1, "price"]) and pd.isna(df.loc[0, "extra"])


def test_json_lines(tmp_path):
    res = load_file(write(tmp_path, "d.json", '{"a": 1}\n{"a": 2, "b": "x"}\n\n'), "d.json")
    assert res.df.shape == (2, 2)


def test_json_wrapped_records(tmp_path):
    res = load_file(write(tmp_path, "d.json", json.dumps({"data": [{"a": 1}, {"a": 2}]})), "d.json")
    assert res.df["a"].tolist() == ["1", "2"]


@pytest.mark.parametrize("bad", ['[{"a": 1},', "{not json}", '"just a string"'])
def test_invalid_json(tmp_path, bad):
    with pytest.raises(AppError) as exc:
        load_file(write(tmp_path, "d.json", bad), "d.json")
    assert exc.value.code in ("invalid_json", "empty_file")


def test_json_streaming_across_chunk_boundaries():
    records = [{"id": i, "text": "x" * 97, "n": 1234567.125} for i in range(30_000)]  # > 3 MB
    res = load_json(io.BytesIO(json.dumps(records).encode()))
    assert res.df.shape == (30_000, 3)
    assert res.df["id"].iloc[-1] == "29999"
    assert res.df["n"].iloc[123] == "1234567.125"


def test_unicode_json(tmp_path):
    res = load_file(write(tmp_path, "d.json", '[{"شہر": "لاہور"}]'), "d.json")
    assert res.df.loc[0, "شہر"] == "لاہور"


# ----------------------------------------------------------------- full workflow per format

@pytest.mark.parametrize("fmt", ["csv", "tsv", "json", "xlsx"])
def test_every_format_supports_the_cleaning_workflow(fresh_store, tmp_path, fmt):
    rows = [["Name", "City"], ["Ali ", "lahore"], ["Ali ", "lahore"], ["Sara", "KARACHI"]]
    if fmt == "xlsx":
        raw = open(make_xlsx(tmp_path, sheets={"S": rows}), "rb").read()
    elif fmt == "json":
        raw = json.dumps([dict(zip(rows[0], r)) for r in rows[1:]]).encode()
    else:
        sep = "," if fmt == "csv" else "\t"
        raw = "\n".join(sep.join(r) for r in rows).encode() + b"\n"
    info = ws.create_session(fresh_store, f"people.{fmt}", raw)
    assert info["file"]["format"] == fmt
    s = fresh_store.get(info["session_id"])
    assert preview_apply(s, RemoveDuplicates(type="remove_duplicates"))["applied"]
    assert preview_apply(s, TrimWhitespace(type="trim_whitespace"))["applied"]
    assert preview_apply(s, StandardizeText(type="standardize_text", columns=["City"], case="title"))["applied"]
    assert s.current["City"].tolist() == ["Lahore", "Karachi"]
    ws.undo(s)
    assert s.current["City"].tolist() == ["lahore", "KARACHI"]
    ws.reset(s)
    assert len(s.current) == 3
    for out_fmt in ("csv", "xlsx"):
        path, name, _ = ws.export_file(s, None, out_fmt)
        assert name == f"people_cleaned.{out_fmt}"
        back = pd.read_csv(path, dtype=str) if out_fmt == "csv" else pd.read_excel(path, dtype=str)
        assert back["Name"].tolist() == ["Ali ", "Ali ", "Sara"]
        import os
        os.remove(path)


# ----------------------------------------------------------------- Excel export safety

def test_excel_export_does_not_create_formulas(fresh_store, tmp_path):
    info = ws.create_session(fresh_store, "f.csv", b"cmd\n=1+1\n=HYPERLINK(\"x\")\n")
    s = fresh_store.get(info["session_id"])
    path, _, _ = ws.export_file(s, None, "xlsx")
    wb = openpyxl.load_workbook(path)
    cell = wb.active["A2"]
    assert cell.value == "=1+1" and cell.data_type == "s"
    import os
    os.remove(path)


def test_excel_export_types_and_missing(fresh_store, tmp_path):
    info = ws.create_session(fresh_store, "data.xlsx", open(make_xlsx(tmp_path), "rb").read())
    s = fresh_store.get(info["session_id"])
    path, _, _ = ws.export_file(s, "out", "xlsx")
    ws_ = openpyxl.load_workbook(path).active
    assert [c.value for c in ws_[1]] == ["ID", "Name", "Joined", "Score", "Active", "Mixed"]
    assert ws_["A2"].value == 1 and ws_["D3"].value is None
    assert ws_["C2"].value == datetime(2024, 1, 5)
    import os
    os.remove(path)


def test_excel_export_row_limit(monkeypatch, fresh_store):
    from app.services import exporters
    monkeypatch.setattr(exporters, "EXCEL_MAX_ROWS", 3)
    info = ws.create_session(fresh_store, "d.csv", b"a\n1\n2\n3\n")
    with pytest.raises(AppError) as exc:
        ws.export_file(fresh_store.get(info["session_id"]), None, "xlsx")
    assert exc.value.code == "excel_too_many_rows"


def test_excel_export_rejects_control_characters(fresh_store):
    info = ws.create_session(fresh_store, "d.csv", b"a\nbad\x01value\n")
    with pytest.raises(AppError) as exc:
        ws.export_file(fresh_store.get(info["session_id"]), None, "xlsx")
    assert exc.value.code == "excel_illegal_characters"


def test_unknown_export_format(fresh_store):
    info = ws.create_session(fresh_store, "d.csv", b"a\n1\n")
    with pytest.raises(AppError):
        ws.export_file(fresh_store.get(info["session_id"]), None, "pdf")
