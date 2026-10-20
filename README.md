# CleanData Studio — Smart Data Cleaning Tool

**Clean Your Data. Trust Your Results.**
A simple and powerful workspace to inspect, clean, and export better datasets.

[![Tests](https://github.com/muneeb548/cleandata-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/muneeb548/cleandata-studio/actions/workflows/tests.yml)

> **© 2026 Raja Muneeb Ahmed. All rights reserved.** This repository is public so the code can be reviewed as a portfolio project. It is not open source: copying, reusing, redistributing or selling it requires written permission. See [LICENSE](LICENSE).

CleanData Studio is a web application for cleaning messy tabular data without writing code. Upload a CSV, TSV, Excel or JSON file (up to 100 MB by default), review a data quality report, preview and apply cleaning operations (with undo and reset), compare before/after statistics, and download the cleaned file as CSV or Excel.

---

## Features

- **Supported formats** — CSV (`.csv`), TSV (`.tsv`, `.tab`), Excel (`.xlsx`, `.xlsm`, legacy `.xls`) and JSON (`.json`: an array of records, JSON Lines, or an object wrapping one list of records). The format is detected from the file name and checked against the file's bytes; it can also be chosen manually under **Import options**, together with the Excel sheet.
- **Upload validation** — 100 MB default limit (configurable, checked in the browser and on the server, including streamed uploads without a declared size); UTF-8, UTF-8 with BOM, UTF-16 and Windows-1252 fallback; delimiter detection; empty, header-only, binary, corrupted and mismatched files rejected with helpful messages; PDFs, images and Word documents refused even if renamed; duplicate and blank column names renamed safely; ragged rows padded without losing data. If the two parsing passes disagree on the number of rows, the import fails instead of dropping records.
- **Faithful import** — CSV/TSV/JSON values are imported as text exactly as written (`007` stays `007`, `3.10` stays `3.10`, JSON numbers keep their original text). Excel columns keep Excel's own types when the whole column agrees (integers, decimals, dates); mixed columns become text. Only truly empty cells count as missing.
- **Data quality overview** — rows, columns, missing cells, duplicate rows, columns with missing values, completeness %, missing-by-column chart, column type distribution, per-column completeness, and a list of detected issues with one-click "Fix".
- **Issue detection** — duplicates, empty rows/columns, missing values, extra spaces, space-only cells, placeholders such as `N/A`/`null`, mixed types, dates stored as text and mixed date formats (with a day-first / month-first hint), inconsistent capitalisation, untidy or invalid email addresses, phone numbers without a country code, country names written in different ways, amounts stored as text (`$1,250.00`, `Rs 1,25,000`), column names with spaces, IQR outliers.
- **⚡ Quick Clean** — proposes every fix that keeps the meaning of the data (exact duplicates when an ID column makes it safe, spaces, placeholders, one spelling per value, emails, country names, phone numbers using each row's country, dates), previews them together and applies them as separate, undoable steps. Missing values, outliers and ambiguous dates are listed for a human decision, never changed.
- **✨ AI assistant (optional, off by default)** — *Ask AI*: describe the cleaning in your own words (English, Urdu, Roman Urdu…) and get a plan made of the app's own operations; *Suggest with AI* fills the Map values table (`Lhr`, `LAHORE` → `Lahore`); *AI summary* writes a plain-language report in the client's language; *Ask a question* answers questions about the data ("which city has the most customers?") with numbers calculated by the app, not by the AI. Runs on a free local model through [Ollama](https://ollama.com) (data never leaves the computer) or on the Claude API (cloud, asks for consent first). See [AI assistant](#ai-assistant).
- **Data preview** — paginated (50/100/200 rows), search across all columns, numeric-aware sorting, inferred types, missing values clearly labelled, original vs working data toggle.
- **Cleaning operations** (all previewable before applying):
  - Remove duplicate rows (keep first / last)
  - Handle missing values (drop rows, drop columns, fill mean, fill median, fill constant) on selected columns only
  - Trim whitespace (selected or all text columns)
  - Standardize text (lower / UPPER / Title case)
  - Clean column names (trim, underscores, optional lowercase, collision-free)
  - Convert data types (integer, decimal, text, datetime) with invalid values reported; choose to stop or set them to missing
  - IQR outlier review (read-only — never modifies data)
  - Remove empty rows / columns
  - Find and replace (exact or contains, case-sensitive option)
  - Map many values at once from a table of the column's distinct values (`Isb`, `ISB` → `Islamabad`)
  - Split a column (Full Name → First + Last, from the start or the end) and merge columns
  - Standardize phone numbers from any country (Google libphonenumber): national, international or E.164 format; the country can come from a column such as `country`
  - Standardize country names or ISO codes for all 249 ISO countries plus Kosovo, with common spellings, local names and three-letter codes
  - Clean email addresses (spaces, capitals, `mailto:`, optional provider typo fixes) and list invalid ones
  - Clean amounts in any currency and number style (`$1,250.00`, `Rs 1,25,000`, `1.234,56 €`, `(500)`) into real numbers, with a warning when one column mixes currencies
  - Find near-duplicates (same record written differently, optional small spelling differences) and flag or remove them
  - Flag rows for review in a new column (missing, invalid email or phone, not a number or date, repeated value) without changing any data
- **Workflow safety** — original dataset never modified; undo last step; reset to original; confirmation dialogs for destructive steps; activity log; operations that change nothing are not recorded as applied.
- **Before/after comparison** — real counts for rows, columns, missing cells, duplicates, completeness, rows/columns removed, cells modified, per-operation log and side-by-side previews.
- **Change report and recipes** — a ready-to-send summary of every change for the client (copy, `.txt`, or a "Cleaning report" sheet in the Excel download), and cleaning recipes: save the applied steps as a `.json` file and apply them to next week's file with one click (the recipe holds only the steps, never data).
- **Export** — CSV (UTF-8, optional BOM for Excel) or Excel `.xlsx`, generated from the current working data and streamed from a temporary file. Text that starts with `=` is stored as text in Excel (never as a formula); Excel's row/column/cell-length limits produce a clear error instead of a truncated file.
- **Large files** — uploads are streamed to a temporary file; CSV/TSV is parsed by pandas' C parser and JSON by a streaming parser; undo history shares unchanged columns between steps (copy-on-write) and keeps older steps only within a memory budget; profiles, column types and sorted views are cached per dataset version.
- **Privacy** — data kept in server memory only (temporary files exist just for the duration of an import or download), random 256-bit session IDs, 30-minute inactivity expiry, no external APIs, no cell values in logs, security headers, rate limiting.
- **Public site** — landing page, features, how it works, operations, privacy, FAQ, about, privacy policy, contact/feedback, 404, SEO meta tags, Open Graph image, favicon, robots.txt, sitemap.xml.

## Technology stack

| Layer | Tools |
|---|---|
| Frontend | React 19, TypeScript, Vite 6, Tailwind CSS 4, shadcn/ui-style components (class-variance-authority), Lucide icons, Recharts |
| Backend | Python 3.11+, FastAPI, pandas, NumPy, Pydantic 2, Uvicorn, openpyxl (Excel .xlsx), xlrd (Excel .xls) |
| Tests | pytest (+ FastAPI TestClient), Vitest + Testing Library |

No database, authentication, paid AI API or cloud service is needed.

## Project structure

```
cleandata-studio/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, error handlers, optional website serving
│   │   ├── web.py               # serves the built frontend (FRONTEND_DIST) with CSP and caching
│   │   ├── core/                # config.py (settings/.env), errors.py (AppError), security.py (headers, client IP, rate limit), middleware.py (HTTPS redirect, rate limit, headers), logging_utils.py (log redaction)
│   │   ├── api/
│   │   │   ├── deps.py          # Session dependency (X-Session-Id verification)
│   │   │   └── routers/         # system, sessions, datasets, operations, history, compare, export
│   │   ├── schemas/
│   │   │   ├── operations.py    # Pydantic request models for every cleaning operation
│   │   │   └── responses.py     # Pydantic response models (OpenAPI docs)
│   │   ├── services/
│   │   │   ├── sessions.py      # In-memory session store, tokens, snapshots, audit log
│   │   │   ├── csv_loader.py    # Streaming CSV/TSV parsing & validation
│   │   │   ├── importers.py     # Format detection, Excel and JSON import
│   │   │   ├── profiling.py     # Statistics, type inference, issue detection
│   │   │   ├── operations.py    # Cleaning operations (pure functions)
│   │   │   ├── workspace.py     # Use cases: preview/apply/undo/history/compare/export
│   │   │   ├── exporters.py     # CSV / Excel export to temporary files
│   │   │   └── memory.py        # Memory estimates for the undo history budget
│   │   └── utils/               # serialization.py (JSON-safe cells), filenames.py (safe names), tempfiles.py (stale temp cleanup)
│   ├── docs/API.md              # Every endpoint with example requests and responses
│   ├── tests/                   # pytest suite
│   ├── requirements.txt         # runtime dependencies (production)
│   ├── requirements-dev.txt     # + pytest, httpx (tests)
│   ├── pytest.ini
│   └── .env.example
├── frontend/
│   ├── public/                  # favicon, og-image
│   ├── seo-plugin.ts            # generates robots.txt + sitemap.xml at build time from VITE_SITE_URL
│   ├── src/
│   │   ├── api/                 # API client + response types
│   │   ├── components/ui/       # Button, Card, Dialog, Toast, form controls…
│   │   ├── components/layout/   # Logo, header, footer
│   │   ├── components/landing/  # Workspace illustration
│   │   ├── content/site.ts      # Marketing copy, features, FAQ
│   │   ├── lib/                 # router, SEO helper, utilities
│   │   ├── pages/               # Landing, Workspace, About, Privacy, Contact, 404
│   │   └── workspace/           # Upload, Overview, Data, Clean, Compare, Export panels
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── .env.example
├── Dockerfile               # one container: builds the frontend, serves website + API
├── .dockerignore
├── production.env.example   # recommended production variables
├── DEPLOYMENT.md            # hosting guide and checklists
├── AUDIT_REPORT.md          # QA / security / UX audit: bugs, fixes, tests and actual results
└── README.md
```

## Prerequisites (Windows)

- **Python 3.11, 3.12 or 3.13** — https://www.python.org/downloads/ (tick "Add python.exe to PATH" during install)
- **Node.js 20 LTS or 22 LTS** — https://nodejs.org/
- Git (optional) — https://git-scm.com/

Check in a new terminal (PowerShell or Command Prompt):

```powershell
python --version
node --version
npm --version
```

## Design system

The interface is built on a small design system documented in [`frontend/DESIGN_SYSTEM.md`](frontend/DESIGN_SYSTEM.md): colour, type-scale and spacing tokens in `frontend/src/index.css`, and shared components (buttons, cards, badges, tables, inputs, dialogs, tooltips, alerts, KPI tiles) in `frontend/src/components/ui/`. The workspace uses a top bar (dataset, Undo, Reset, Replace file, Download), a desktop sidebar for the five workflow views, and horizontal navigation on tablets and phones.

## Installation and running

You need **two terminals**: one for the backend, one for the frontend.

### 1. Backend (terminal 1)

```powershell
cd cleandata-studio\backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

> If PowerShell refuses to run `activate`, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or use Command Prompt (`cmd`) instead.

The API is now at http://127.0.0.1:8000 — interactive docs at http://127.0.0.1:8000/docs.

### 2. Frontend (terminal 2)

```powershell
cd cleandata-studio\frontend
copy .env.example .env
npm install
npm run dev
```

Open **http://localhost:5173**. During development, Vite forwards `/api` requests to the backend on port 8000, so no CORS setup is needed.

### Production build of the frontend

```powershell
cd cleandata-studio\frontend
npm run build
npm run preview
```

The static site is written to `frontend/dist/`. When hosting the frontend and backend on different domains, set `VITE_API_BASE_URL` in `frontend/.env` and add the frontend origin to `CORS_ORIGINS` in `backend/.env`. Configure your web server to serve `index.html` for unknown paths (single-page app routing).

## Running tests

Backend:

```powershell
cd cleandata-studio\backend
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
```

Real large-file tests (about 1 minute, ~1.5 GB RAM; they generate a ~99 MB CSV, a >100 MB CSV and a 60 MB JSON Lines file in a temporary folder):

```powershell
$env:CLEANDATA_LARGE_TESTS=1
pytest tests\test_large_files.py -s
Remove-Item Env:CLEANDATA_LARGE_TESTS
```

(Command Prompt: `set CLEANDATA_LARGE_TESTS=1` then `pytest tests\test_large_files.py -s`.)

Frontend:

```powershell
cd cleandata-studio\frontend
npm test
npm run typecheck
```

End-to-end workflow test (real browser, real backend — upload → profile → preview → apply → history → compare → download → undo → reset, plus error cases). Start the backend and `npm run dev` first, then in a third terminal:

```powershell
cd cleandata-studio\frontend
npx playwright install chromium   # first time only
npm run e2e
```

It computes the expected cleaned data itself and compares it with the downloaded files. Use `$env:E2E_URL="http://localhost:4173"` to test `npm run preview` instead, or `$env:E2E_HEADED=1` to watch the browser.

## Configuration

`backend/.env` (all optional):

| Variable | Default | Meaning |
|---|---|---|
| `MAX_UPLOAD_MB` | 100 | Upload size limit (browser and server) |
| `SESSION_TTL_MINUTES` | 30 | Inactive sessions are deleted after this time |
| `MAX_SESSIONS` | 10 | Least recently used dataset is removed beyond this number |
| `MAX_HISTORY_SNAPSHOTS` | 20 | Maximum undo steps kept |
| `MAX_HISTORY_MEMORY_MB` | 1024 | Memory budget for older undo steps (the original, current and previous versions are always kept) |
| `MAX_PAGE_SIZE` | 200 | Maximum rows per preview page |
| `RATE_LIMIT_PER_MINUTE` | 240 | API requests per IP per minute |
| `UPLOAD_LIMIT_PER_MINUTE` | 20 | Uploads per IP per minute |
| `CORS_ORIGINS` | localhost:5173 (production: empty) | Allowed frontend origins (only needed when the website is on a different domain than the API) |
| `ENVIRONMENT` | development | `production` turns off `/docs`, turns on HSTS and refuses to start with an unsafe configuration |
| `FRONTEND_DIST` | (empty) | Path to `frontend/dist`; the API server then also serves the website (one origin) |
| `ENABLE_API_DOCS` | on in development | Interactive docs at `/docs` |
| `HSTS_SECONDS` | 31536000 in production | `Strict-Transport-Security` max-age |
| `FORCE_HTTPS` | false | Redirect `http://` to `https://` (uses the proxy's `X-Forwarded-Proto`; `/api/health` is never redirected) |
| `CLIENT_IP_HEADER` | (empty) | Proxy header with the visitor's IP, used for rate limiting (e.g. `X-Real-IP`) |
| `MAX_TOTAL_MEMORY_MB` | 0 (off) | Memory budget for all datasets together |
| `SESSION_PROTECT_SECONDS` | 0 | Datasets used within this time are never removed to make room; new uploads get "server busy" instead |
| `MAX_CONCURRENT_UPLOADS` | 0 (unlimited) | Uploads processed at the same time |
| `LOG_LEVEL` | INFO | Python log level |

`frontend/.env` (all optional): `VITE_API_BASE_URL`, `VITE_CONTACT_EMAIL` (enables the contact form), `VITE_GITHUB_URL`, `VITE_SITE_URL` (used at build time for canonical URLs, `robots.txt` and `sitemap.xml`).

Recommended production values: [`production.env.example`](production.env.example).

## API endpoints

Full reference with example requests and real example responses: **[`backend/docs/API.md`](backend/docs/API.md)**. Interactive docs: `http://127.0.0.1:8000/docs`.

All endpoints except health/config/upload/operations catalog require the header `X-Session-Id` with the token returned by the upload.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/config` | Upload limit, session lifetime, formats |
| POST | `/api/upload?filename=&format=&sheet=` | Upload raw file bytes → **201** with session token |
| GET | `/api/session` | File info, shapes, history, audit log |
| DELETE | `/api/session` | Delete the session and its data → **204** |
| GET | `/api/profile?dataset=current\|original&light=` | Quality statistics, column profiles, detected issues |
| GET | `/api/rows?dataset=&page=&page_size=&search=&sort_by=&sort_dir=` | Paginated rows |
| GET | `/api/outliers?column=` | IQR outlier report (read-only) |
| GET | `/api/operations` | Catalog of cleaning operations with parameter schemas |
| POST | `/api/operations/preview` | Preview an operation; returns a `preview_token` |
| POST | `/api/operations/apply` | Apply an operation (data-removing operations require the `preview_token`, else **428**) |
| GET | `/api/history` | Active steps and full audit log (applied / undone / reset) |
| POST | `/api/undo` | Undo the last operation (**409** if nothing to undo) |
| POST | `/api/reset` | Restore the original upload |
| GET | `/api/compare` | Before/after statistics |
| GET | `/api/compare/rows?page=&page_size=&changes_only=` | Row-level comparison with changed cells flagged |
| GET | `/api/export?filename=&format=csv\|xlsx&bom=&protect_formulas=` | Download the working data |
| GET | `/api/ai/status` | Is the AI assistant on and ready, where does it run, what is shared |
| POST | `/api/ai/plan` | Plain-language request → validated cleaning steps (nothing is changed) |
| POST | `/api/ai/map-values` | Suggested value mapping for one column |
| POST | `/api/ai/summary` | Plain-language report of the cleaning |
| POST | `/api/ai/ask` | Answer a question about the data (the AI writes a query plan, the app computes it) |

## AI assistant

The AI is **off by default**; the app works fully without it. It has four features: **Ask AI** and **Ask a question** (Overview page), **Suggest with AI** (Map values form) and **AI summary** (Download page).

For questions, the AI only fills in a small query plan (filters, up to two group-by columns, one calculation such as count, sum or average). The app checks that every column exists and calculates the result with pandas, then shows the table and the steps used, so no number in an answer is invented by the model.

**How it stays safe.** The model never runs code and never receives the whole file. It gets a short description (column names, types, counts and, unless `AI_SEND_VALUES=false`, up to 20 example values per column) and must answer with JSON that matches a fixed schema. Every proposed step is checked with the same validation as the normal API, must use real columns, and is tried on a sample first; anything else is dropped and shown as "left out by the safety check". Nothing changes until you preview and press Apply, and each step can be undone. Prompts and answers are not logged.

### Free local AI with Ollama (recommended, data stays on your computer)

1. Install Ollama from <https://ollama.com/download> (Windows installer) and open it.
2. In PowerShell, download a model (about 2 GB, once):
   ```powershell
   ollama pull qwen2.5:3b
   ```
3. In `backend\.env` set:
   ```
   AI_PROVIDER=ollama
   ```
4. Restart the backend. **Ask AI** appears on the Overview page.

`qwen2.5:3b` runs on a laptop with 8 GB RAM without a graphics card; answers take roughly 20 seconds to 2 minutes. On a weaker machine try `AI_MODEL=qwen2.5:1.5b` (faster, less accurate); with 16 GB RAM `qwen2.5:7b` gives better plans.

### Claude API (cloud, paid — for a hosted version)

Set `AI_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=...` (from <https://console.anthropic.com>). The default model is `claude-haiku-5-5` (change with `AI_MODEL`). The data description is sent to Anthropic, so every request needs the user's consent (a checkbox in the app; `consent: true` in the API). `AI_MAX_CALLS_PER_SESSION` (default 30) limits cost per uploaded file. If your users' data is personal data under GDPR or similar laws, check Anthropic's data processing terms and tell your users in your privacy policy.

## Security and privacy

- An upload is streamed to a private temporary file (in the system temp folder) and deleted as soon as the import finishes or fails; downloads are written to a temporary file and deleted after sending. Datasets are otherwise kept only in memory and never stored in a database.
- Data is never sent to external AI services or third-party APIs, unless you turn on the optional cloud AI (`AI_PROVIDER=anthropic`); then only a description of the data is sent, and only after the user ticks a consent box. The default AI option (Ollama) runs on the same computer.
- Each upload returns a session token `<id>.<secret>` (2 × 256 random bits). The server keeps only a SHA-256 hash of the secret and compares it in constant time; a malformed token, the public id alone, or another session's secret is rejected with 404. Sessions expire after `SESSION_TTL_MINUTES` of inactivity (a background task removes them every minute) or when deleted. Restarting the server deletes all data.
- Operations that can remove rows or columns can only be applied with a `preview_token` from a preview of the exact same operation on the same data version (HMAC with a per-session key), so data loss is always previewed first — even when the API is called directly.
- The original upload is never modified; each applied step stores a snapshot (unchanged columns are shared, not copied), so Undo restores the exact previous data instead of recomputing it.
- Uploaded content is only parsed as data — never executed. Client-provided filenames are reduced to a base name, and the server only reads and writes its own temporary files (names chosen by `tempfile`, never by the client).
- Logs contain event names and counts only, never cell values. Uvicorn's access log is filtered so query strings (which can contain search terms or file names) are replaced by `?…`. Unexpected errors return a generic message with an error id (no stack traces).
- Temporary upload/export files left behind by a crash are deleted at startup and hourly (only files named `cleandata_upload_*` / `cleandata_export_*` older than one hour).
- Excel uploads are parsed with `defusedxml` (required; the server refuses .xlsx without it) and checked for "zip bombs" (archives that expand to more than 1 GB, or are suspiciously compressed) before parsing. Files with more than 5,000 columns are rejected.
- **Spreadsheet formula injection:** text such as `=HYPERLINK(...)` in a CSV can be executed when the file is opened in Excel. The quality report flags such values, and the CSV download has an optional *Protect against spreadsheet formulas* setting (`protect_formulas=true`) that prefixes them with `'`. It is off by default because it changes values. Excel (.xlsx) downloads always store them as text.
- Security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, CSP for API responses) and per-IP rate limits are applied.
- Because files are processed by a server, they **do** leave the user's device. When you run the app locally, that server is your own computer.

## In-memory storage and multiple workers

Sessions are stored in the memory of **one Python process**. This keeps uploaded data off disk and is simple to run, but it has consequences:

- **Restart = data loss.** Restarting or reloading the server (including `uvicorn --reload` after a code change) deletes every session. Users must upload again.
- **Run exactly one worker.** With `uvicorn --workers 4` or `gunicorn -w 4`, each worker has its own memory. A request routed to a different worker than the upload will get **404 session expired**, and undo/history would be inconsistent. The same applies to multiple containers behind a load balancer without sticky sessions. Rate limits are also per process.
- **Memory is the capacity limit.** Every session holds its original data, the working data and undo snapshots. `MAX_SESSIONS` (default 10) and `MAX_HISTORY_MEMORY_MB` bound this; the least recently used session is removed when the limit is reached.
- **Scaling out** would require moving datasets to shared storage (e.g. Parquet files in object storage or a Redis/DB-backed store) and keying sessions there; this is a listed future improvement.

## Big file mode

Text cells are stored with Apache Arrow (`pyarrow`, installed from `requirements.txt`) instead of one Python object per cell, and CSV files are parsed in chunks of 200,000 rows that are converted before the next chunk is read. Both cut the memory a large file needs. Undo snapshots share every unchanged column, also with Arrow storage. Set `STRING_STORAGE=python` in `backend/.env` to go back to the old storage.

Measure how much memory a file size needs on your computer (run in `backend` with the virtual environment active):

```powershell
python scripts/measure_memory.py 300                                   # Arrow storage (default)
$env:STRING_STORAGE="python"; python scripts/measure_memory.py 100     # old storage, for comparison
Remove-Item Env:STRING_STORAGE
```

Choose `MAX_UPLOAD_MB` so that the reported peak memory stays well below your free RAM.

## Measured large-file performance

Measured on a Linux machine with 2 CPU cores and 8 GB RAM (your laptop may be faster or slower). These are **real** runs on generated files, not simulations:

| File | Rows | Import | Quality report | Peak memory (whole process) |
|---|---|---|---|---|
| CSV, 99.7 MB, 8 columns | 1,132,358 | 2.6 s | 10.6 s | ~0.9 GB after 8 operations |
| JSON array, 103.6 MB (nested) | 520,000 | 3.4 s | 5.8 s | ~0.45 GB |
| JSON Lines, 103.6 MB | 520,000 | 3.2 s | 6.0 s | ~0.45 GB |
| Excel .xlsx, 22.8 MB | 500,000 (4M cells) | 46.6 s | 5.8 s | ~0.45 GB |

In the browser test (Chromium), uploading and analysing the 99.7 MB CSV took about 15 s; sorting 1.1M rows ~1 s; duplicate removal (preview + apply) ~3 s; undo ~3 s; CSV download ~4 s. The downloaded file contained every row and was identical to the upload apart from line endings. A 101 MB file was rejected in the browser before uploading. JSON files above 100 MB were imported in the tests above by calling the importer directly; through the app they are rejected by the 100 MB limit.

## Known limitations

- **Memory:** with the old `STRING_STORAGE=python` mode a 100 MB CSV becomes roughly 0.5 GB in memory (all values kept as text). The default mode stores text with Apache Arrow (`pyarrow`), which needs several times less; measure your own machine with `python scripts/measure_memory.py 300` (see *Big file mode*). Each session also keeps the original data plus undo steps (within `MAX_HISTORY_MEMORY_MB`). On a laptop with 8 GB RAM, work with one large file at a time. If memory runs out, Python may report an error (shown as "not enough memory") or Windows may slow down heavily.
- **Excel import is slow** (openpyxl reads roughly 80–100 thousand cells per second here): a full-size sheet (1M rows × 8 columns) can take 1–2 minutes. Formulas are imported as their last saved values; password-protected workbooks are not supported. Only one sheet is loaded per upload.
- **Legacy .xls** support uses `xlrd`; it is implemented but was **not tested with a real .xls file** in development (only the error paths were tested), because no .xls generator was available. Please try one of your own `.xls` files.
- **Excel export** is limited by Excel itself to 1,048,575 data rows and 16,384 columns and is slower than CSV (~1 minute for a full sheet). Larger results must be downloaded as CSV.
- **JSON** objects that wrap the records (e.g. `{"data": [...]}`) are loaded fully into memory before conversion; arrays and JSON Lines are streamed.
- While the server computes a quality report for a large dataset (~10 s for 1M rows), other requests from the same server can wait, because pandas holds Python's global lock.
- Sessions live in a single server process's memory: they are lost on restart and are not shared between multiple workers. Run one Uvicorn worker.
- **Reverse proxies:** if you deploy behind nginx, set `client_max_body_size 100m;` (default is 1 MB) and generous `proxy_read_timeout`; other proxies have similar settings. The Vite dev server, Uvicorn and FastAPI do not impose their own body limit.
- Processing cannot be cancelled once the upload has finished; the upload itself can be cancelled.
- Datetime conversion relies on pandas parsing; ambiguous formats (e.g. 01/02/2024) should use the "day comes first" option or an explicit format.
- The contact form opens the visitor's email app; there is no email backend.

## Future improvements

Faster Excel reading (e.g. the optional `python-calamine` engine), Arrow-backed strings to cut memory use, automated profiling reports, saved projects and user accounts, cloud storage, team collaboration, custom validation rules, scheduled cleaning jobs, data pipeline integrations, and a blog with guides (for example "How to Clean CSV Files" and "How to Handle Missing Values"). New public pages can be added in `frontend/src/App.tsx`, `PUBLIC_PAGES` in `frontend/seo-plugin.ts` (sitemap) and `SPA_ROUTES` in `backend/app/web.py`.

## Deployment

See **[DEPLOYMENT.md](DEPLOYMENT.md)**: recommended hosting, exact steps, environment variables, HTTPS, limits, in-memory session behaviour, monitoring, custom domains, and deployment / production-testing checklists. The root `Dockerfile` builds one container that serves both the website and the API.
