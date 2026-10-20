"""Measure how much memory a large CSV needs in CleanData Studio.

Creates a realistic customer CSV of the requested size (or uses your own file), imports it
the same way an upload does, runs a few cleaning steps and prints time and memory.

Run from the backend folder (with the virtual environment active):

    python scripts/measure_memory.py 300              # make and test a 300 MB file
    python scripts/measure_memory.py --file big.csv   # test your own file

Compare storage modes by setting STRING_STORAGE before running:

    $env:STRING_STORAGE="python"; python scripts/measure_memory.py 100
    $env:STRING_STORAGE="auto";   python scripts/measure_memory.py 100

The generated file is written to your temporary folder and deleted at the end.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def peak_memory_mb() -> float:
    """Highest memory use of this process so far (Windows, Linux and macOS)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # Without these declarations ctypes passes the 64-bit process handle as a 32-bit int.
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        get_info = kernel32.K32GetProcessMemoryInfo
        get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        get_info.restype = wintypes.BOOL
        if not get_info(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return 0.0
        return counters.PeakWorkingSetSize / 2**20
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 2**20 if sys.platform == "darwin" else peak / 1024


FIRST = ["Ali", "Sara", "John", "Maria", "Ahmed", "Fatima", "Wei", "Priya", "Lukas", "Amara", "Omar", "Emma"]
LAST = ["Khan", "Smith", "Garcia", "Chen", "Patel", "Müller", "Okafor", "Silva", "Ahmed", "Brown"]
CITIES = ["Lahore", "lahore", "LAHORE ", "Karachi", "London", "New York", "Berlin", "São Paulo", "Lagos", "Dubai", ""]
COUNTRIES = ["Pakistan", "PK", "UK", "United States", "Germany", "Brazil", "Nigeria", "UAE", ""]


def make_csv(path: Path, megabytes: int) -> int:
    rnd = random.Random(42)
    target = megabytes * 2**20
    rows = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write("customer_id,name,email,phone,city,country,amount,signup_date,notes\n")
        while f.tell() < target:
            lines = []
            for _ in range(5000):
                rows += 1
                first, last = rnd.choice(FIRST), rnd.choice(LAST)
                email = f" {first}.{last}{rows}@GMAIL.com " if rows % 7 == 0 else f"{first.lower()}.{last.lower()}{rows}@gmail.com"
                phone = rnd.choice([f"0300 {rnd.randint(1000000, 9999999)}", f"+44 20 {rnd.randint(1000, 9999)} {rnd.randint(1000, 9999)}", ""])
                amount = rnd.choice([f"${rnd.randint(1, 9999)}.{rnd.randint(0, 99):02d}", f"\"Rs {rnd.randint(1, 999)},{rnd.randint(100, 999)}\"", ""])
                date = rnd.choice([f"2024-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}", f"{rnd.randint(1, 28):02d}/{rnd.randint(1, 12):02d}/2024"])
                note = rnd.choice(["", "VIP", "called twice", '"asked for refund, then cancelled"'])
                lines.append(f"{rows},{first} {last},{email},{phone},{rnd.choice(CITIES)},{rnd.choice(COUNTRIES)},{amount},{date},{note}\n")
            f.write("".join(lines))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("megabytes", nargs="?", type=int, default=100, help="size of the generated file (default 100)")
    parser.add_argument("--file", help="measure this CSV instead of a generated one")
    args = parser.parse_args()

    from app.schemas.operations import RemoveDuplicates, TrimWhitespace
    from app.services.csv_loader import STRING_DTYPE
    from app.services.importers import load_file
    from app.services.memory import frame_bytes
    from app.services.operations import run_operation

    generated = None
    if args.file:
        path = Path(args.file)
    else:
        fd, name = tempfile.mkstemp(suffix=".csv", prefix="cleandata_measure_")
        os.close(fd)
        path = generated = Path(name)
        print(f"Creating a {args.megabytes} MB test file…")
        rows = make_csv(path, args.megabytes)
        print(f"  {rows:,} rows")

    try:
        size_mb = path.stat().st_size / 2**20
        print(f"Text storage: {STRING_DTYPE.storage}   File: {size_mb:,.1f} MB")
        start = time.perf_counter()
        df = load_file(str(path), path.name).df
        print(f"Import:            {time.perf_counter() - start:6.1f} s   data in memory ≈ {frame_bytes(df) / 2**20:,.0f} MB"
              f"   ({df.shape[0]:,} rows × {df.shape[1]} columns)")
        start = time.perf_counter()
        trimmed = run_operation(df, TrimWhitespace(type="trim_whitespace")).df
        print(f"Trim whitespace:   {time.perf_counter() - start:6.1f} s")
        start = time.perf_counter()
        deduped = run_operation(trimmed, RemoveDuplicates(type="remove_duplicates")).df
        print(f"Remove duplicates: {time.perf_counter() - start:6.1f} s")
        print(f"Peak memory of the whole process: {peak_memory_mb():,.0f} MB")
        del df, trimmed, deduped
    finally:
        if generated is not None:
            generated.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
