"""Streaming import for delimited text files (CSV and TSV).

Design decisions
----------------
* Every cell is imported as *text* (pandas "string" dtype). pandas' automatic
  type guessing can silently change data ("007" -> 7, "3.10" -> 3.1), so raw
  text is kept and exported unchanged unless the user applies an operation.
  Column types are still inferred for display and validation.
* Only truly empty cells are treated as missing. Placeholders such as "N/A"
  are reported as a data quality issue instead of being changed silently.
* Large files: the file is never read into one big string. Encoding is checked
  with an incremental decoder, a first streaming pass (Python's C-implemented
  csv module) measures the structure (header, widest row, blank lines), and the
  values are then parsed by pandas' C parser straight into string columns.
  The two passes must agree on the number of rows; otherwise the import fails
  loudly instead of losing records.
"""

from __future__ import annotations

import codecs
import csv
import io
from dataclasses import dataclass, field
from typing import BinaryIO

import pandas as pd

from app.core.config import settings
from app.core.errors import AppError

# A single cell may legitimately be large; never let the csv module reject it.
csv.field_size_limit(2**31 - 1)


def _string_dtype() -> pd.StringDtype:
    """How text cells are stored in memory (STRING_STORAGE in backend/.env).

    "pyarrow" keeps a column's text in one compact Apache Arrow buffer and uses several
    times less memory than "python" (one Python object per cell), which is what makes
    large files fit on a laptop. "auto" (default) uses pyarrow when it is installed.
    """
    choice = settings.string_storage
    if choice != "python":
        try:
            import pyarrow  # noqa: F401

            return pd.StringDtype("pyarrow")
        except ImportError:
            pass
    return pd.StringDtype("python")


STRING_DTYPE = _string_dtype()
# Rows parsed at a time. Each chunk is converted to compact storage before the next is
# read, so a large file never exists as millions of Python objects at once.
CSV_CHUNK_ROWS = 200_000
CANDIDATE_DELIMITERS = [",", ";", "\t", "|"]
DELIMITER_NAMES = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}
READ_CHUNK = 1024 * 1024


@dataclass
class LoadResult:
    df: pd.DataFrame
    encoding: str | None
    delimiter: str | None
    format: str = "csv"
    warnings: list[str] = field(default_factory=list)
    sheet: str | None = None
    sheets: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- encoding

def _decodes_as(f: BinaryIO, encoding: str) -> bool:
    f.seek(0)
    decoder = codecs.getincrementaldecoder(encoding)()
    try:
        while chunk := f.read(READ_CHUNK):
            decoder.decode(chunk)
        decoder.decode(b"", final=True)
        return True
    except UnicodeDecodeError:
        return False


def detect_encoding(f: BinaryIO) -> tuple[str, list[str]]:
    f.seek(0)
    head = f.read(8192)
    if head.startswith(b"PK\x03\x04") or head.startswith(b"\xd0\xcf\x11\xe0"):
        raise AppError("not_csv", "This file looks like an Excel workbook or other binary document, not CSV text.",
                       "If it is an Excel file, upload it with an .xlsx or .xls extension (or choose the Excel format).",
                       status=415)
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", []
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        if _decodes_as(f, "utf-16"):
            return "utf-16", ["File was UTF-16 encoded; it was converted to UTF-8."]
    if b"\x00" in head:
        raise AppError("binary_file", "This file contains binary data and cannot be read as text.",
                       "Make sure you are uploading a plain-text CSV or TSV file.", status=415)
    if _decodes_as(f, "utf-8"):
        return "utf-8", []
    if _decodes_as(f, "cp1252"):
        return "cp1252", ["File is not UTF-8. It was read as Windows-1252; check special characters."]
    return "latin-1", ["File is not UTF-8. It was read as Latin-1; check special characters."]


def _text(f: BinaryIO, encoding: str) -> io.TextIOWrapper:
    f.seek(0)
    return io.TextIOWrapper(f, encoding=encoding, newline="")


def detect_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters="".join(CANDIDATE_DELIMITERS)).delimiter
    except csv.Error:
        pass
    lines = [line for line in sample.splitlines()[:20] if line.strip()]
    best, best_score = ",", 0
    for delim in CANDIDATE_DELIMITERS:
        counts = [line.count(delim) for line in lines]
        if counts and min(counts) > best_score:
            best, best_score = delim, min(counts)
    return best


# --------------------------------------------------------------------------- headers

def clean_headers(header: list[str], warnings: list[str]) -> list[str]:
    """Fill blank names and make every name unique without colliding."""
    names: list[str] = []
    blank = 0
    for i, value in enumerate(header):
        name = "" if value is None else str(value)
        if name.strip() == "":
            blank += 1
            name = f"column_{i + 1}"
        names.append(name)
    if blank:
        warnings.append(f"{blank} column(s) had no header and were named column_N.")

    used: set[str] = set()
    result: list[str] = []
    renamed = 0
    for name in names:
        candidate, n = name, 1
        while candidate in used or (candidate != name and candidate in names):
            n += 1
            candidate = f"{name}_{n}"
        if candidate != name:
            renamed += 1
        used.add(candidate)
        result.append(candidate)
    if renamed:
        warnings.append(f"{renamed} duplicate column name(s) were renamed with a numeric suffix (e.g. name_2).")
    return result


# --------------------------------------------------------------------------- structure pass

@dataclass
class _Structure:
    header: list[str]
    leading_records: list[int]  # field counts of records before the header
    lengths: dict[int, int]  # field count -> number of data records
    blank_inside: int
    trailing_blank: int

    @property
    def header_width(self) -> int:
        return len(self.header)


def _scan(f: BinaryIO, encoding: str, delimiter: str) -> _Structure:
    text = _text(f, encoding)
    try:
        reader = csv.reader(text, delimiter=delimiter, strict=False)
        header: list[str] | None = None
        leading: list[int] = []
        lengths: dict[int, int] = {}
        pending_blank = 0  # blank records seen since the last non-blank data record
        blank_inside = 0
        for record in reader:
            if header is None:
                if any(cell.strip() for cell in record):
                    header = record
                else:
                    leading.append(len(record))
                continue
            # pandas skips lines that are empty or contain only whitespace when
            # blank lines are skipped (multi-column files); mirror that here.
            is_blank = len(record) == 0 or (len(header) > 1 and len(record) == 1 and not record[0].strip())
            if is_blank:
                pending_blank += 1
                continue
            blank_inside += pending_blank
            if pending_blank:
                lengths[0] = lengths.get(0, 0) + pending_blank
            pending_blank = 0
            lengths[len(record)] = lengths.get(len(record), 0) + 1
    except csv.Error as exc:
        raise AppError("malformed_csv", "The file could not be parsed as delimited text.",
                       "Check for unbalanced quotation marks, then export the file again.") from exc
    finally:
        text.detach()
    if header is None:
        raise AppError("empty_file", "The file contains no data.", "Upload a file with a header row.")
    return _Structure(header, leading, lengths, blank_inside, pending_blank)


# --------------------------------------------------------------------------- public API

def load_delimited(f: BinaryIO, *, delimiter: str | None = None, fmt: str = "csv") -> LoadResult:
    """Load CSV/TSV from a seekable binary stream (a temp file or BytesIO)."""
    f.seek(0, io.SEEK_END)
    if f.tell() == 0:
        raise AppError("empty_file", "The file is empty.", "Check that you exported the data correctly and try again.")

    encoding, warnings = detect_encoding(f)
    text = _text(f, encoding)
    sample = text.read(65536)
    text.detach()
    if sample.strip() == "":
        raise AppError("empty_file", "The file contains no data, only blank space.", "Upload a file with a header row.")
    if delimiter is None:
        delimiter = detect_delimiter(sample)

    st = _scan(f, encoding, delimiter)
    multi = st.header_width > 1
    data_lengths = {k: v for k, v in st.lengths.items() if not (multi and k == 0)}
    expected_rows = sum(data_lengths.values())
    widest = max([st.header_width, *data_lengths.keys()])
    if multi and st.lengths.get(0):
        warnings.append(f"{st.lengths[0]} blank line(s) without any values were skipped.")

    # Rows pandas will emit before the header: whitespace-only records always,
    # completely blank lines only when blank lines are kept (single column).
    lead = sum(1 for n in st.leading_records if n > 1 or not multi)

    f.seek(0)
    try:
        reader = pd.read_csv(
            f,
            sep=delimiter,
            header=None,
            names=list(range(widest)),
            dtype=STRING_DTYPE,
            encoding=encoding,
            keep_default_na=False,
            na_values=[""],
            skip_blank_lines=multi,
            engine="c",
            quotechar='"',
            doublequote=True,
            chunksize=CSV_CHUNK_ROWS,
        )
        with reader:
            chunks = list(reader)
        if not chunks:
            df = pd.DataFrame({i: pd.array([], dtype=STRING_DTYPE) for i in range(widest)})
        else:
            df = chunks[0] if len(chunks) == 1 else pd.concat(chunks, ignore_index=True)
        del chunks
    except (pd.errors.ParserError, ValueError, UnicodeDecodeError) as exc:
        raise AppError("malformed_csv", "The file could not be parsed as delimited text.",
                       "Check for unbalanced quotation marks or mixed separators, then export again.") from exc
    except MemoryError as exc:
        raise AppError("out_of_memory", "There is not enough memory to load this file.",
                       "Close other programs, or split the file into smaller parts.", status=507) from exc

    df = df.iloc[lead + 1:]
    if not multi and st.trailing_blank:
        df = df.iloc[: len(df) - st.trailing_blank] if st.trailing_blank <= len(df) else df.iloc[:0]
    if len(df) != expected_rows:
        raise AppError(
            "inconsistent_parse",
            f"The file could not be read reliably ({len(df):,} rows parsed, {expected_rows:,} expected).",
            "The file may mix quoting styles. Re-export it as a standard CSV and try again. "
            "Nothing was imported, so no data was lost silently.",
        )

    header = st.header + [""] * (widest - st.header_width)
    if widest > st.header_width:
        warnings.append(
            f"Some rows had more values than the header; {widest - st.header_width} extra column(s) were added so no data is lost."
        )
    short = sum(v for k, v in data_lengths.items() if 0 < k < widest)
    if short:
        warnings.append(f"{short:,} row(s) had fewer values than the header; missing cells were left empty.")

    df.columns = clean_headers(header, warnings)
    df.index = pd.RangeIndex(len(df))
    if len(df) == 0:
        warnings.append("The file contains a header row but no data rows.")
    if delimiter not in (",", "\t") or (delimiter == "\t" and fmt != "tsv"):
        warnings.append(f"Detected {DELIMITER_NAMES.get(delimiter, repr(delimiter))}-separated values.")
    return LoadResult(df=df, encoding=encoding, delimiter=delimiter, format=fmt, warnings=warnings)


def load_csv(raw: bytes, max_bytes: int | None = None, *, delimiter: str | None = None, fmt: str = "csv") -> LoadResult:
    """Convenience wrapper for in-memory bytes (used by tests)."""
    if max_bytes is not None and len(raw) > max_bytes:
        raise AppError("file_too_large", f"The file is larger than the {max_bytes / (1024 * 1024):g} MB limit.",
                       "Split the file into smaller parts or remove unneeded columns.", status=413)
    return load_delimited(io.BytesIO(raw), delimiter=delimiter, fmt=fmt)
