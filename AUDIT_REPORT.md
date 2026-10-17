# CleanData Studio — QA, Security and UX Audit

Date: 2026-10-17. Scope: whole project (frontend, backend, data integrity, security, UX).
Every result below comes from a command that was actually run. Anything that could not be run is listed under "Not verified".

## 1. Bugs found

| # | Area | Severity | Bug |
|---|---|---|---|
| 1 | Security / privacy | High | Uvicorn's access log printed full URLs, so search terms typed in the data preview (`/api/rows?search=…`, i.e. cell values) and file names ended up in server logs. |
| 2 | Security | High | `.xlsx` files were parsed without `defusedxml` and without a size check of the unzipped content: an "XML bomb" / "zip bomb" workbook could exhaust memory. |
| 3 | Security | Medium | CSV formula injection: values such as `=HYPERLINK(...)` were neither flagged nor could they be neutralised in a CSV download (Excel can execute them on open). |
| 4 | Robustness | Medium | No limit on column count; a file with hundreds of thousands of columns could make profiling and the UI unusable. |
| 5 | Privacy | Low | Temporary upload/export files left behind by a crash or forced kill were never cleaned up. |
| 6 | Data correctness (UX) | Medium | The "Fix" button for placeholder values always pre-filled Find & Replace with `N/A`, even when the detected placeholder was e.g. `?` or `-`, so the suggested fix did nothing. |
| 7 | Frontend / TypeScript | Medium | Type error in `ColumnPicker` (`disabledReason` callback typed for the wrong option type) — `npm run typecheck` would fail. Recharts formatter parameters were implicitly `any`. |
| 8 | Frontend / build | Low | `baseUrl` in `tsconfig.json` is deprecated in current TypeScript and produced an error; replaced by a relative `paths` mapping. |
| 9 | Accessibility | Medium | Text contrast below WCAG AA (4.5:1) in many places (`text-slate-400` labels, placeholders, footer headings, type badges, step numbers in the workspace sidebar at 4.32:1). |
| 10 | Accessibility | Low | Heading levels skipped (h1 → h3) in cards and preview results; toast close button smaller than 24×24 px. |
| 11 | Text | Low | Grammar: "1 value start with =" in the new formula issue. |
| 12 | Tests | Low | Two new audit tests imported `app.main` (needs FastAPI), so they could not run without FastAPI; one round-trip test asserted a specific quoting style instead of the values. |

## 2. Bugs fixed

All 12 above are fixed:

1. `app/core/logging_utils.py` — `RedactQueryString` filter on `uvicorn.access` replaces query strings with `?…`.
2. `app/services/importers.py` — `.xlsx` is refused (501) if `defusedxml` is missing; the archive is checked before parsing (rejected with 413 if it expands to more than 1 GB, or more than 50 MB with a compression ratio above 200). `defusedxml` added to `requirements.txt`.
3. `app/services/profiling.py` flags formula-like text (`=`, `+`, `-`, `@`, but not numbers such as `-5`) as a "Review" issue; `app/services/exporters.py` + `GET /api/export?protect_formulas=true` + a new opt-in checkbox in the Download view prefix such values with `'`. Off by default because it changes values. Excel downloads store all of them as text (verified: cell type `s`).
4. `app/services/workspace.py` — more than 5,000 columns → 422 `too_many_columns` with a hint.
5. `app/utils/tempfiles.py` — files named `cleandata_upload_*` / `cleandata_export_*` older than one hour are deleted at startup and hourly.
6. The server now sends one real affected value (`example`) with each placeholder issue; the frontend pre-fills Find & Replace with it (empty if none).
7. `ColumnPicker` made generic; formatter parameters typed.
8. `tsconfig.json` uses `"paths": { "@/*": ["./src/*"] }` without `baseUrl`.
9. Contrast raised (`slate-400` → `slate-500/600`); re-audit shows no remaining violations.
10. `CardTitle` is an `h2`, preview headings `h3`; toast close button 28×28 px.
11. Wording fixed (singular/plural).
12. Helpers moved to FastAPI-free modules; round-trip test compares parsed values.

## 3. Tests and checks executed

| Check | Command / tool |
|---|---|
| Backend unit + integration tests | `python -m pytest -q` (backend) |
| Large-file tests (100 MB CSV/JSON, 500k-row xlsx) | `CLEANDATA_LARGE_TESTS=1 python -m pytest tests/test_large_files.py` |
| Operation fuzzing | script running every operation variant on 14 edge-case datasets (duplicates, missing, empty rows/cols, whitespace, mixed types, invalid dates, Unicode, commas/quotes/newlines, duplicate headers, one row, zero rows, …) checking: no crash, preview never mutates, preview = apply summary, undo restores exactly, original never changes, reset export = upload |
| App wiring | importing `app.main` with a stand-in `fastapi` package (route registration and annotations) |
| Frontend logic tests | `utils.test.ts`, `operationForms.test.ts`, `client.test.ts` bundled with esbuild and run in Node |
| TypeScript | `tsc --noEmit` with strict settings over all `src/**/*.ts(x)` (stub type declarations for React/Lucide/Recharts/vitest) |
| End-to-end browser test | `frontend/e2e/workflow.mjs` (Playwright, Chromium) against the built frontend + backend services |
| Accessibility audit | Playwright script: unnamed controls, duplicate ids, unlabeled inputs, heading order, WCAG contrast, target size, console errors — 11 views at 1440 px and 390 px |
| Responsive check | horizontal overflow on every view at 768 px and 390 px |
| Link check | every internal link and anchor on public pages |
| New-fix browser check | placeholder "Fix" pre-fill, formula checkbox, downloaded file content |

## 4. Actual results

- **pytest: 184 passed, 4 skipped, 0 failed.** Skipped: `tests/test_api.py` (30 HTTP tests — FastAPI is not installable in this sandbox) and 3 opt-in large tests.
- **Large tests: 3 passed** (55 s).
- **Fuzzing: 378 runs — 136 applied, 202 no-change, 20 blocked as invalid, 20 rejected with a clear error, 0 crashes.** Preview never changed data; undo and reset were exact; the original was never modified. 2 byte-level differences, both harmless: a missing cell in a one-column file is written as `""` (needed, otherwise the row would vanish), and a trailing blank line in a one-column file is not kept.
- **App import: OK, 17 API routes registered.**
- **Frontend logic tests: 25 passed, 0 failed.**
- **TypeScript: 0 errors** (after fixes #7, #8).
- **E2E: 17/17 steps passed** — landing → upload → invalid file → profile → paging/search → validation → blocked conversion → trim (preview/apply/history) → duplicate removal with confirmation → compare → download content check → undo → reset (exact) → stale preview rejected → server unreachable → expired session → replace file → no JS errors.
- **Accessibility: 0 issues** at 1440 px and 390 px (after fixes #9, #10).
- **Overflow: none** at 768 px and 390 px; no console errors.
- **Links: all 11 internal links/anchors resolve** (the skip-link `#main` was correctly reported as an in-page anchor).
- **New fixes in the browser:** placeholder `?` pre-filled correctly; checkbox off by default; with it on, the download was `Karachi,'=1+1` while `-5` style numbers stayed unchanged.

## 5. Features verified end to end (browser + backend services)

Upload with validation and progress; data quality overview with real stats and issues; paginated, searchable, sortable preview; all cleaning operations through preview/apply; confirmation and server-enforced preview for data-removing operations; history and activity log; undo; reset to original; before/after comparison; CSV download content; session expiry handling; network failure handling; starting over (session deletion); formula protection; placeholder fix pre-fill.

## 6. Not verified (could not be run here)

- **The real FastAPI HTTP layer** (`tests/test_api.py`, 30 tests): FastAPI/Uvicorn could not be installed (package registry blocked). The browser tests ran against a Starlette stand-in that calls the same service functions and validates every response against the same Pydantic models — close, but not FastAPI itself. Run `python -m pytest` on your laptop: these 30 tests will then run.
- **`npm install`, `npm run build`, real `tsc` with the real `@types` packages, and the vitest component tests** (`*.test.tsx`).
- **Real Lucide icons and Recharts charts** — rendered with stand-ins here.
- **A real legacy `.xls` file** (only error paths tested).
- **Windows itself**, and Firefox/Safari.

## 7. Security and privacy limitations

- Files are processed by the server, so they do leave the user's device (when run locally, that server is the user's own computer).
- Data is kept in one process's memory: lost on restart, not shared between workers — run one worker.
- No authentication: anyone who can reach the server can upload. Sessions are protected by unguessable tokens, but a stolen token (e.g. from the browser's `sessionStorage`) gives access until the session expires (30 min of inactivity).
- Rate limits are per process and per IP; no protection against a distributed flood.
- Temporary files exist on disk for the duration of an upload/export (plaintext, in the OS temp folder).
- Formula protection for CSV is opt-in.
- HTTPS, HSTS and proxy limits must be configured by whoever deploys it.

## 8. Run on Windows

See README → "Installation and running" and "Running tests". Short version:

```powershell
# Terminal 1 — backend
cd cleandata-studio\backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
copy .env.example .env
pytest
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd cleandata-studio\frontend
copy .env.example .env
npm install
npm test
npm run typecheck
npm run dev
# open http://localhost:5173

# Terminal 3 (optional) — browser end-to-end test, with both servers running
cd cleandata-studio\frontend
npx playwright install chromium
npm run e2e
```
