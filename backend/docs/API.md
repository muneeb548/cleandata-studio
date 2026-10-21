# CleanData Studio API

Base URL (local): `http://127.0.0.1:8000`. Interactive docs generated from the code: **`/docs`** (Swagger UI) and **`/redoc`**.

Every response body in this document was produced by running the real backend service functions (the same ones the routes call) on the sample file below, then shortened where marked with `…`. Session tokens and preview tokens are random and will differ on your machine.

```csv
Name ,City,Age
  Ali ,Lahore,25
Sara,lahore,
Sara,lahore,
Omar,KARACHI,31
```

## Conventions

- **Session token.** `POST /api/upload` returns `session_id`, a token of the form `<id>.<secret>` (two independent 256-bit random values). Send it as the `X-Session-Id` header on every other session endpoint. The server stores only a SHA-256 hash of the secret and compares it in constant time, so the public id alone, a guessed value or a token from another session is rejected.
- **Errors** always have this shape (no stack traces):

  ```json
  {"error": {"code": "file_too_large", "message": "The file is larger than the 100 MB limit.", "hint": "Split the file into smaller parts or remove unneeded columns."}}
  ```

| Status | When |
|---|---|
| 200 | Success |
| 201 | Upload accepted, session created |
| 204 | Session deleted |
| 400 | Invalid file content, unknown column, incompatible operation (e.g. mean of a text column) |
| 401 | `X-Session-Id` header missing |
| 404 | Session unknown, token invalid, or session expired |
| 409 | Nothing to undo; `preview_token` outdated |
| 308 | Plain-HTTP request redirected to HTTPS (only with `FORCE_HTTPS=true`; never for `/api/health`) |
| 413 | File larger than `MAX_UPLOAD_MB`, or a dataset larger than the whole `MAX_TOTAL_MEMORY_MB` budget (`file_too_large_for_server`) |
| 415 | Unsupported or corrupted file type |
| 422 | Request parameters invalid; operation blocked (e.g. values that cannot be converted); Excel export limits |
| 428 | An operation that can remove data was applied without previewing it first |
| 429 | Rate limit exceeded |
| 500 | Unexpected error (generic message + error id; details only in the server log, without cell values) |
| 503 | `server_busy`: too many uploads at once (`MAX_CONCURRENT_UPLOADS`) or the memory budget is full of datasets in active use — try again later |
| 507 | Not enough memory to load the file |

- **Cells** in JSON are strings, numbers, booleans or `null` (missing). Row numbers are 1-based positions in the uploaded file and stay stable after rows are removed.

---

## System

### `GET /api/health`
```json
{"status": "ok"}
```

### `GET /api/config`
```json
{"max_upload_mb": 100, "session_ttl_minutes": 30, "max_page_size": 200, "formats": ["csv", "tsv", "xlsx", "xls", "json"], "export_formats": ["csv", "xlsx"]}
```

---

## Sessions

### `POST /api/upload?filename=people.csv[&format=csv|tsv|xlsx|xls|json][&sheet=Sheet1]` → 201

Body: the raw file bytes. Format is detected from the extension and verified against the file content (`format` overrides). The body is streamed to a temporary file and rejected as soon as it exceeds the limit, even without a `Content-Length` header.

```bash
curl -X POST "http://127.0.0.1:8000/api/upload?filename=people.csv" \
     -H "Content-Type: application/octet-stream" --data-binary @people.csv
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/upload?filename=people.csv" `
  -ContentType "application/octet-stream" -InFile .\people.csv
```

Response:
```json
{
  "session_id": "Wk3…<id>.<secret>…9Q",
  "file": {
    "name": "people.csv",
    "size": 74,
    "encoding": "utf-8",
    "delimiter": ",",
    "format": "csv",
    "format_label": "CSV",
    "sheet": null,
    "sheets": [],
    "warnings": []
  },
  "original_shape": {
    "rows": 4,
    "columns": 3
  },
  "current_shape": {
    "rows": 4,
    "columns": 3
  },
  "history": [],
  "log": [],
  "can_undo": false,
  "expires_in_seconds": 1800
}
```

Errors: 400 `empty_file`, `malformed_csv`, `invalid_json`, `inconsistent_parse`; 413 `file_too_large`; 415 `invalid_extension`, `unsupported_content`, `binary_file`, `corrupt_file`, `not_csv`; 507 `out_of_memory`.

### `GET /api/session`
Same object as the upload response without `session_id`. `history` lists active steps; `log` is the audit trail (applied / undone / reset).

### `DELETE /api/session` → 204
Deletes the session and its data immediately. Idempotent (204 even if it was already gone).

---

## Other files (Combine files)

### `POST /api/files?filename=orders.csv[&format=…][&sheet=…]` → 201

Adds another file to the current session (header `X-Session-Id`), with the same body format,
validation and size limit as `POST /api/upload`. At most 10 files per session; they are kept in
memory only and count towards the server's memory budget. Returns `{"file": {...}, "session": {...}}`;
`file` has `id`, `name`, `size`, `format`, `sheet`, `rows`, `columns`, `warnings`, `added_at`.
`GET /api/session` lists added files under `files`.

### `GET /api/files/{file_id}[?rows=10]`

The file's details plus `preview: {columns, rows}` with its first rows (max 50).

### `DELETE /api/files/{file_id}`

Removes the file and returns the session info. Steps already applied with it keep their result.

### Combining: the `combine_files` operation

Preview and apply it like any other operation:

```json
{"operation": {"type": "combine_files", "file_id": "3f2a9c1b7d4e", "mode": "append", "source_column": "source_file"}}
{"operation": {"type": "combine_files", "file_id": "3f2a9c1b7d4e", "mode": "join",
               "keys": [{"left": "email", "right": "Email"}], "how": "left",
               "loose_keys": true, "duplicates": "first", "columns": ["city"], "suffix": "_2"}}
```

- `append`: rows of the other file go below the working data; columns are matched by name. A column
  in only one file is empty for the other file's rows; a column with different types becomes text.
  Blocked when the files share no column name.
- `join`: `how` = `left` (keep every row), `inner` (only matched rows; can remove rows, so it needs a
  preview token) or `outer` (also add unmatched rows of the other file). `duplicates` = `first` (like
  VLOOKUP) or `all` (one row per match). Empty keys never match. Brought columns whose name already
  exists get `suffix`. Results above 5 million rows / 100 million cells are blocked.
- Existing rows keep their row numbers; added rows get new numbers after the highest one.
- `changes.added_rows` in the preview shows a sample of the rows that would be added.
- Recipes and "continue where you left off" leave these steps out (they never contain the other
  file); the AI assistant never plans them.

## Dataset

### `GET /api/profile?dataset=current|original[&light=true]`
Quality statistics computed from every cell. `completeness` and `missing_pct` are `null` when the dataset has no rows/cells. `light=true` skips issue detection and unique counts (fast; used by forms). Shortened example:
```json
{
  "stats": {
    "rows": 4,
    "columns": 3,
    "total_cells": 12,
    "missing_cells": 2,
    "duplicate_rows": 1,
    "columns_with_missing": 1,
    "completeness": 83.33,
    "empty_rows": 0,
    "empty_columns": 0
  },
  "columns": [
    {
      "name": "Name ",
      "type": "text",
      "missing": 0,
      "missing_pct": 0.0,
      "completeness": 100.0,
      "unique": 3,
      "is_text": true
    },
    {
      "name": "City",
      "type": "text",
      "missing": 0,
      "missing_pct": 0.0,
      "completeness": 100.0,
      "unique": 3,
      "is_text": true
    }
  ],
  "type_distribution": {
    "text": 2,
    "integer": 1
  },
  "issues": [
    {
      "id": "missing:Age",
      "severity": "high",
      "title": "2 missing values in \"Age\"",
      "description": "50.0% of this column is empty.",
      "column": "Age",
      "count": 2,
      "suggested_operation": "missing_values"
    },
    {
      "id": "duplicates",
      "severity": "medium",
      "title": "1 duplicate row",
      "description": "Rows that are exact copies of an earlier row.",
      "column": null,
      "count": 1,
      "suggested_operation": "remove_duplicates"
    }
  ],
  "dataset": "current"
}
```

### `GET /api/rows?dataset=current&page=1&page_size=100[&search=…][&sort_by=Age&sort_dir=desc]`
`page_size` is capped at `MAX_PAGE_SIZE` (200). Numeric text columns are sorted numerically; missing values sort last.
```json
{
  "dataset": "current",
  "columns": [
    {
      "name": "Name ",
      "type": "text"
    },
    {
      "name": "City",
      "type": "text"
    },
    {
      "name": "Age",
      "type": "integer"
    }
  ],
  "rows": [
    [
      "  Ali ",
      "Lahore",
      "25"
    ],
    [
      "Sara",
      "lahore",
      null
    ]
  ],
  "row_numbers": [
    1,
    2
  ],
  "page": 1,
  "page_size": 2,
  "total_rows": 4,
  "unfiltered_rows": 4,
  "total_pages": 2
}
```

### `GET /api/outliers?column=Salary`
IQR report (Q1 − 1.5·IQR, Q3 + 1.5·IQR). Read-only. 400 `not_numeric` / `too_few_values`, 404 unknown column.

---

## Operations

### `GET /api/operations`
All eight operations with parameter schemas (generated from the Pydantic request models). First entry:
```json
[
  {
    "type": "remove_duplicates",
    "label": "Remove duplicate rows",
    "description": "Delete rows that are exact copies of another row.",
    "may_remove_data": true,
    "parameters": {
      "keep": {
        "default": "first",
        "description": "Which copy of each duplicate group to keep.",
        "enum": [
          "first",
          "last"
        ],
        "title": "Keep",
        "type": "string"
      }
    },
    "required": []
  }
]
```

| `type` | Parameters | Can remove data |
|---|---|---|
| `remove_duplicates` | `keep`: first \| last | yes |
| `missing_values` | `strategy`: drop_rows \| drop_columns \| fill_mean \| fill_median \| fill_constant; `columns`; `value` (fill_constant) | drop_* only |
| `trim_whitespace` | `columns` (empty = all text columns) | no |
| `standardize_text` | `columns`; `case`: lower \| upper \| title | no |
| `clean_column_names` | `replace_spaces`, `lowercase` | no |
| `convert_type` | `columns`; `target`: integer \| float \| string \| datetime; `on_error`: abort \| set_missing; `date_format`; `dayfirst` | no (invalid values are reported; with `abort` nothing is applied) |
| `remove_empty` | `target`: rows \| columns \| both | yes |
| `find_replace` | `columns`; `find`; `replace` (empty = missing); `match`: exact \| contains; `case_sensitive` | no |

Validation: unknown fields are rejected (422), strings and column lists have size limits, `date_format` may only contain valid `%` directives. Data-dependent rules (column exists, column is numeric/text) return 400 with a specific `code`.

### `POST /api/operations/preview`
```json
{"operation": {"type": "remove_duplicates", "keep": "first"}}
```
Runs the operation on the working data **without saving it**:
```json
{
  "operation": {
    "type": "remove_duplicates",
    "label": "Remove duplicate rows",
    "params": {
      "type": "remove_duplicates",
      "keep": "first"
    }
  },
  "summary": "Removed 1 duplicate row (kept the first occurrence).",
  "warnings": [],
  "blocked": null,
  "destructive": true,
  "changed": true,
  "rows_before": 4,
  "rows_after": 3,
  "columns_before": 3,
  "columns_after": 3,
  "rows_removed": 1,
  "columns_removed": 0,
  "cells_changed": 0,
  "changes": {
    "cell_samples": [],
    "removed_rows": {
      "columns": [
        "Name ",
        "City",
        "Age"
      ],
      "row_numbers": [
        3
      ],
      "rows": [
        [
          "Sara",
          "lahore",
          null
        ]
      ]
    },
    "removed_columns": [],
    "mapping": null
  },
  "details": {},
  "preview_token": "e06173f665ff20646fc734eea37d795951949209"
}
```

`preview_token` is an HMAC of the exact operation parameters and the current dataset version.

### `POST /api/operations/apply`
```json
{"operation": {"type": "remove_duplicates", "keep": "first"}, "preview_token": "e06173f665ff20646fc734eea37d795951949209"}
```
- Operations that can remove rows or columns **must** include the `preview_token` from their preview, otherwise **428**:
```json
{
  "error": {
    "code": "preview_required",
    "message": "This operation can remove data, so it must be previewed before it is applied.",
    "hint": "Call the preview endpoint first and send its preview_token with the apply request."
  }
}
```
- A token from a different operation or an older dataset version returns **409** `preview_outdated`.
- An operation that would change nothing returns `"applied": false` and is not recorded.
- A blocked conversion (`on_error: "abort"` with invalid values) returns **422** `operation_blocked`; nothing changes.

Response (`session` omitted):
```json
{
  "operation": {
    "type": "remove_duplicates",
    "label": "Remove duplicate rows",
    "params": {
      "type": "remove_duplicates",
      "keep": "first"
    }
  },
  "summary": "Removed 1 duplicate row (kept the first occurrence).",
  "warnings": [],
  "blocked": null,
  "destructive": true,
  "changed": true,
  "rows_before": 4,
  "rows_after": 3,
  "columns_before": 3,
  "columns_after": 3,
  "rows_removed": 1,
  "columns_removed": 0,
  "cells_changed": 0,
  "changes": {
    "cell_samples": [],
    "removed_rows": {
      "columns": [
        "Name ",
        "City",
        "Age"
      ],
      "row_numbers": [
        3
      ],
      "rows": [
        [
          "Sara",
          "lahore",
          null
        ]
      ]
    },
    "removed_columns": [],
    "mapping": null
  },
  "details": {},
  "applied": true,
  "step_id": "ac0559615dd4",
  "session": "…same shape as GET /api/session…"
}
```

---

## History

### `GET /api/history`
After applying two operations (remove duplicates, then title-case City):
```json
{
  "steps": [
    {
      "id": "ac0559615dd4",
      "type": "remove_duplicates",
      "label": "Remove duplicate rows",
      "params": {
        "type": "remove_duplicates",
        "keep": "first"
      },
      "summary": "Removed 1 duplicate row (kept the first occurrence).",
      "applied_at": 1792246597.0077224,
      "rows_before": 4,
      "rows_after": 3,
      "columns_before": 3,
      "columns_after": 3,
      "rows_removed": 1,
      "columns_removed": 0,
      "cells_changed": 0,
      "warnings": [],
      "undoable": true
    },
    {
      "id": "d26f706d1add",
      "type": "standardize_text",
      "label": "Standardize text case",
      "params": {
        "type": "standardize_text",
        "columns": [
          "City"
        ],
        "case": "title"
      },
      "summary": "Converted 2 values to Title Case.",
      "applied_at": 1792246597.009248,
      "rows_before": 3,
      "rows_after": 3,
      "columns_before": 3,
      "columns_after": 3,
      "rows_removed": 0,
      "columns_removed": 0,
      "cells_changed": 2,
      "warnings": [],
      "undoable": true
    }
  ],
  "log": [
    {
      "event": "applied",
      "at": 1792246597.0077224,
      "step_id": "ac0559615dd4",
      "type": "remove_duplicates",
      "label": "Remove duplicate rows",
      "summary": "Removed 1 duplicate row (kept the first occurrence)."
    },
    {
      "event": "applied",
      "at": 1792246597.009248,
      "step_id": "d26f706d1add",
      "type": "standardize_text",
      "label": "Standardize text case",
      "summary": "Converted 2 values to Title Case."
    }
  ],
  "can_undo": true
}
```

### `POST /api/undo`
Restores the dataset exactly as it was before the last step (the snapshot is stored, not recomputed). 409 `cannot_undo` when there is nothing to undo or the previous snapshot was dropped to respect `MAX_HISTORY_MEMORY_MB`.
```json
{
  "undone": {
    "id": "d26f706d1add",
    "type": "standardize_text",
    "label": "Standardize text case",
    "params": {
      "type": "standardize_text",
      "columns": [
        "City"
      ],
      "case": "title"
    },
    "summary": "Converted 2 values to Title Case.",
    "applied_at": 1792246597.009248,
    "rows_before": 3,
    "rows_after": 3,
    "columns_before": 3,
    "columns_after": 3,
    "rows_removed": 0,
    "columns_removed": 0,
    "cells_changed": 2,
    "warnings": [],
    "undoable": true
  },
  "session": "…"
}
```

### `POST /api/reset`
Restores the original upload (which is never modified) and clears the active steps. The reset is recorded in `log`.
```json
{
  "steps_removed": 1,
  "session": "…"
}
```

---

## Compare

### `GET /api/compare`
```json
{
  "original": {
    "rows": 4,
    "columns": 3,
    "total_cells": 12,
    "missing_cells": 2,
    "duplicate_rows": 1,
    "columns_with_missing": 1,
    "completeness": 83.33,
    "empty_rows": 0,
    "empty_columns": 0
  },
  "current": {
    "rows": 3,
    "columns": 3,
    "total_cells": 9,
    "missing_cells": 1,
    "duplicate_rows": 0,
    "columns_with_missing": 1,
    "completeness": 88.89,
    "empty_rows": 0,
    "empty_columns": 0
  },
  "rows_removed": 1,
  "columns_removed": 0,
  "cells_modified": 0,
  "operations": [
    {
      "id": "ac0559615dd4",
      "type": "remove_duplicates",
      "label": "Remove duplicate rows",
      "params": {
        "type": "remove_duplicates",
        "keep": "first"
      },
      "summary": "Removed 1 duplicate row (kept the first occurrence).",
      "applied_at": 1792246597.0077224,
      "rows_before": 4,
      "rows_after": 3,
      "columns_before": 3,
      "columns_after": 3,
      "rows_removed": 1,
      "columns_removed": 0,
      "cells_changed": 0,
      "warnings": [],
      "undoable": true
    }
  ],
  "preview": "…first 20 rows of each dataset…"
}
```

### `GET /api/compare/rows?page=1&page_size=50[&changes_only=true]`
Original and current rows aligned by row number. `current: null` = row removed; `changed[i]` refers to `current_columns[i]` (renamed columns are listed in `renamed_or_new` and not compared).
```json
{
  "original_columns": [
    "Name ",
    "City",
    "Age"
  ],
  "current_columns": [
    "Name ",
    "City",
    "Age"
  ],
  "renamed_or_new": [],
  "rows": [
    {
      "row": 3,
      "original": [
        "Sara",
        "lahore",
        null
      ],
      "current": null,
      "changed": null
    }
  ],
  "page": 1,
  "page_size": 50,
  "total_rows": 1,
  "total_pages": 1,
  "changes_only": true
}
```

---

## Export

### `GET /api/export?format=csv|xlsx[&filename=people_clean][&bom=true][&protect_formulas=true]`
Streams the **current working data** as an attachment (`Content-Disposition` with a sanitised name; path segments and reserved characters are removed). CSV is UTF-8 with standard quoting (`bom=true` adds a byte-order mark for Excel; `protect_formulas=true` prefixes text that starts with `=`, `+`, `-` or `@` — and is not a number — with `'` so spreadsheet apps do not evaluate it). Excel: text starting with `=` is stored as text; 422 when Excel limits are exceeded. After the reset above, the export equals the upload:

```csv
Name ,City,Age
  Ali ,Lahore,25
Sara,lahore,
Sara,lahore,
Omar,KARACHI,31
```
