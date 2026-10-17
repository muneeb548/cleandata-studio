"""Safe output file names: no paths, no reserved characters, sensible default."""

from __future__ import annotations

import re

_KNOWN_EXT = r"\.(csv|tsv|tab|xlsx|xlsm|xls|json|jsonl|ndjson)$"


def safe_output_name(requested: str | None, original_name: str, ext: str = ".csv") -> str:
    base = (requested or "").strip()
    if not base:
        stem = re.sub(_KNOWN_EXT, "", original_name, flags=re.IGNORECASE)
        base = f"{stem}_cleaned"
    base = re.split(r"[\\/]", base)[-1]
    base = re.sub(_KNOWN_EXT, "", base, flags=re.IGNORECASE)
    base = re.sub(r"[^\w.\- ]", "_", base, flags=re.UNICODE).strip(" .")[:100]
    return f"{base or 'cleaned_data'}{ext}"
