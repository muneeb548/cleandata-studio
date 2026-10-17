import pandas as pd
import pytest

from app.core.errors import AppError
from app.services.importers import validate_filename

from .conftest import MB, MESSY_CSV, load


def test_valid_csv_upload():
    res = load(MESSY_CSV)
    assert res.df.shape == (6, 5)
    assert list(res.df.columns) == ["Name ", "City", "Age", "Salary", "Joined"]
    assert res.encoding == "utf-8"
    # Values are kept exactly as written, including the stray spaces.
    assert res.df.loc[0, "Name "] == "  Ali "


def test_empty_file_rejected():
    with pytest.raises(AppError) as exc:
        load(b"")
    assert exc.value.code == "empty_file"


def test_whitespace_only_file_rejected():
    with pytest.raises(AppError) as exc:
        load("\n\n   \n")
    assert exc.value.code == "empty_file"


def test_header_only_file():
    res = load("a,b,c\n")
    assert res.df.shape == (0, 3)
    assert any("no data rows" in w for w in res.warnings)


def test_utf8_bom_is_removed_from_first_header():
    res = load("\ufeffid,name\n1,Ali\n".encode("utf-8"))
    assert list(res.df.columns) == ["id", "name"]
    assert res.encoding == "utf-8-sig"


def test_windows_1252_fallback():
    res = load("name,city\nJosé,Málaga\n".encode("cp1252"))
    assert res.df.loc[0, "name"] == "José"
    assert res.encoding == "cp1252"
    assert res.warnings


def test_unicode_text_preserved():
    res = load("naam,shehar\nمحمد,لاہور\n李,北京\n")
    assert res.df.loc[0, "naam"] == "محمد"
    assert res.df.loc[1, "shehar"] == "北京"


def test_semicolon_delimiter_detected():
    res = load("a;b;c\n1;2;3\n4;5;6\n")
    assert res.delimiter == ";"
    assert res.df.shape == (2, 3)


def test_quoted_commas_and_newlines():
    res = load('id,comment\n1,"Hello, world"\n2,"line one\nline two"\n')
    assert res.df.loc[0, "comment"] == "Hello, world"
    assert res.df.loc[1, "comment"] == "line one\nline two"


def test_duplicate_column_names_renamed_safely():
    res = load("a,a,b,a\n1,2,3,4\n")
    assert list(res.df.columns) == ["a", "a_2", "b", "a_3"]
    assert res.df.loc[0, "a_3"] == "4"


def test_blank_headers_named():
    res = load(",b,\n1,2,3\n")
    assert list(res.df.columns) == ["column_1", "b", "column_3"]


def test_ragged_rows_do_not_lose_data():
    res = load("a,b\n1,2,3\n4\n")
    assert res.df.shape == (2, 3)
    assert res.df.loc[0, "column_3"] == "3"
    assert pd.isna(res.df.loc[1, "b"])
    assert len(res.warnings) >= 2


def test_leading_zeros_are_preserved():
    res = load("code\n007\n042\n")
    assert res.df["code"].tolist() == ["007", "042"]


def test_only_empty_cells_are_missing():
    res = load("a,b\n,N/A\nx,null\n")
    assert pd.isna(res.df.loc[0, "a"])
    assert res.df.loc[0, "b"] == "N/A"  # placeholders are reported, not silently changed


def test_size_limit_enforced():
    with pytest.raises(AppError) as exc:
        load("a\n" + "x\n" * 100, max_bytes=50)
    assert exc.value.code == "file_too_large"
    assert exc.value.status == 413


def test_excel_file_rejected_with_hint():
    with pytest.raises(AppError) as exc:
        load(b"PK\x03\x04binarystuff")
    assert exc.value.code == "not_csv"


def test_binary_file_rejected():
    with pytest.raises(AppError) as exc:
        load(b"a,b\n\x00\x01\x02")
    assert exc.value.code == "binary_file"


@pytest.mark.parametrize("name", ["data.pdf", "photo.png", "report.docx", "data.txt", "data", "", None])
def test_invalid_extensions(name):
    with pytest.raises(AppError):
        validate_filename(name)


def test_filename_path_is_stripped():
    assert validate_filename("C:\\Users\\me\\..\\secret\\data.CSV") == "data.CSV"
    assert validate_filename("../../etc/data.csv") == "data.csv"


def test_file_just_under_limit_is_accepted():
    body = "a\n" + "x\n" * 10
    assert load(body, max_bytes=len(body.encode())).df.shape == (10, 1)
    assert MB == 1024 * 1024


def test_blank_line_in_single_column_file_is_a_missing_value():
    res = load("a\n1\n\n3\n")
    assert len(res.df) == 3
    assert pd.isna(res.df.loc[1, "a"])


def test_all_empty_rows_are_kept_for_review():
    res = load("a,b\n1,2\n,\n")
    assert len(res.df) == 2
    assert res.df.loc[1].isna().all()
