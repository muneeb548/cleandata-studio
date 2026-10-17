"""Logging helpers. Logs must never contain uploaded data or cell values."""

import logging


class RedactQueryString(logging.Filter):
    """Uvicorn's access log prints full URLs. Query strings can contain cell values
    (e.g. ?search=…) and file names, so only the path is kept."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3 and isinstance(record.args[2], str):
            args = list(record.args)
            args[2] = args[2].split("?", 1)[0] + ("?…" if "?" in args[2] else "")
            record.args = tuple(args)
        return True
