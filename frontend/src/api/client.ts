import type {
  AppConfig,
  ApplyResult,
  ChangeReport,
  ColumnValues,
  CompareResult,
  CompareRowsPage,
  DatasetKind,
  ExportFormat,
  HistoryItem,
  HistoryResponse,
  ImportFormat,
  Operation,
  OperationPreview,
  QuickCleanPlan,
  QuickCleanPreview,
  QuickCleanResult,
  OutlierReport,
  Profile,
  RowsPage,
  SessionInfo,
  UploadResponse,
} from "./types";

/**
 * Backend location. Empty = same origin (in development Vite proxies /api to
 * the FastAPI server, see vite.config.ts). Only public settings belong in
 * VITE_* variables: they are embedded in the built JavaScript.
 */
const BASE = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "").replace(/\/$/, "");
/** Default request timeout. Large datasets can take a while to profile, so it is generous. */
const TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS) || 120_000;
const SESSION_KEY = "cleandata.session";

/** Error with a user-facing message and an optional suggestion, as sent by the API. */
export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public status: number,
    public hint: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Errors that mean the session is gone and the user must upload again. */
export const SESSION_GONE = new Set(["session_expired", "no_session"]);

/** Fired on window whenever any request finds that the session no longer exists. */
export const SESSION_ENDED_EVENT = "cleandata:session-ended";

export function parseErrorBody(status: number, body: unknown): ApiError {
  const err = (body as { error?: { code?: string; message?: string; hint?: string | null } } | null)?.error;
  if (err?.message) return new ApiError(err.message, err.code ?? "error", status, err.hint ?? null);
  if (status === 0) {
    return new ApiError(
      "Cannot reach the CleanData Studio server.",
      "network_error",
      0,
      import.meta.env.DEV
        ? "Check that the backend is running (uvicorn on port 8000) and that VITE_API_BASE_URL is correct, then try again."
        : "Check your internet connection. The service may also be restarting — try again in a minute.",
    );
  }
  if (status === 413) return new ApiError("The file is too large for the server.", "file_too_large", status, null);
  if (status === 429) return new ApiError("Too many requests.", "rate_limited", status, "Wait a minute and try again.");
  if (status === 502 || status === 503 || status === 504)
    return new ApiError("The server is temporarily unavailable.", "unavailable", status, "Try again in a moment.");
  return new ApiError("The server returned an unexpected response.", "unexpected", status, "Please try again.");
}

export function timeoutError(): ApiError {
  return new ApiError(
    "The server took too long to respond.",
    "timeout",
    0,
    "Large files can take a while. Try again; if it keeps happening, use a smaller file.",
  );
}

/** fetch with a timeout; network failures and timeouts become ApiError. */
async function send(url: string, init: RequestInit, timeoutMs = TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch {
    if (controller.signal.aborted) throw timeoutError();
    throw parseErrorBody(0, null);
  } finally {
    window.clearTimeout(timer);
  }
}

// The session id lives in sessionStorage: it survives a page refresh but is
// scoped to this browser tab and cleared when the tab is closed.
export const sessionStore = {
  get(): string | null {
    try {
      return window.sessionStorage.getItem(SESSION_KEY);
    } catch {
      return null;
    }
  },
  set(id: string) {
    try {
      window.sessionStorage.setItem(SESSION_KEY, id);
    } catch {
      /* storage unavailable (private mode): the session still works until refresh */
    }
  },
  clear() {
    try {
      window.sessionStorage.removeItem(SESSION_KEY);
    } catch {
      /* ignore */
    }
  },
};

let memorySessionId: string | null = null;

export function getSessionId(): string | null {
  return memorySessionId ?? sessionStore.get();
}

export function setSessionId(id: string | null) {
  memorySessionId = id;
  if (id) sessionStore.set(id);
  else sessionStore.clear();
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs?: number): Promise<T> {
  const headers = new Headers(init.headers);
  const sid = getSessionId();
  if (sid) headers.set("X-Session-Id", sid);
  if (init.body && typeof init.body === "string") headers.set("Content-Type", "application/json");

  const response = await send(`${BASE}${path}`, { ...init, headers }, timeoutMs);
  if (response.status === 204) return null as T;
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await response.json().catch(() => null) : null;
  if (!response.ok) {
    const error = parseErrorBody(response.status, body);
    if (SESSION_GONE.has(error.code) && sid) window.dispatchEvent(new CustomEvent(SESSION_ENDED_EVENT));
    throw error;
  }
  if (body === null) throw new ApiError("The server sent an empty or invalid response.", "invalid_response", response.status, "Please try again.");
  return body as T;
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== "") search.set(k, String(v));
  });
  const s = search.toString();
  return s ? `?${s}` : "";
}

export type UploadOptions = { format?: ImportFormat | null; sheet?: string | null };

/** Upload with progress reporting (fetch cannot report upload progress, XHR can). */
export function uploadFile(file: File, options: UploadOptions = {}, onProgress?: (fraction: number) => void, signal?: AbortSignal) {
  return new Promise<UploadResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/api/upload${qs({ filename: file.name, format: options.format, sheet: options.sheet?.trim() })}`);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as UploadResponse);
      else reject(parseErrorBody(xhr.status, xhr.response));
    };
    xhr.onerror = () => reject(parseErrorBody(0, null));
    // No overall timeout: big files on slow connections can legitimately take minutes.
    xhr.onabort = () => reject(new ApiError("Upload cancelled.", "aborted", 0));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(file);
  });
}

export const api = {
  config: () => request<AppConfig>("/api/config"),
  session: () => request<SessionInfo>("/api/session"),
  /** 204 No Content; resolves to null. */
  endSession: () => request<null>("/api/session", { method: "DELETE" }),
  profile: (dataset: DatasetKind, light = false) => request<Profile>(`/api/profile${qs({ dataset, light: light || undefined })}`),
  rows: (p: {
    dataset: DatasetKind;
    page: number;
    pageSize: number;
    search?: string;
    sortBy?: string | null;
    sortDir?: "asc" | "desc";
  }) =>
    request<RowsPage>(
      `/api/rows${qs({
        dataset: p.dataset,
        page: p.page,
        page_size: p.pageSize,
        search: p.search,
        sort_by: p.sortBy,
        sort_dir: p.sortDir,
      })}`,
    ),
  outliers: (column: string) => request<OutlierReport>(`/api/outliers${qs({ column })}`),
  values: (column: string) => request<ColumnValues>(`/api/values${qs({ column })}`),
  quickCleanPlan: () => request<QuickCleanPlan>("/api/quick-clean/plan"),
  quickCleanPreview: (operations: Operation[]) =>
    request<QuickCleanPreview>("/api/quick-clean/preview", { method: "POST", body: JSON.stringify({ operations }) }),
  quickCleanApply: (operations: Operation[], previewToken: string) =>
    request<QuickCleanResult>("/api/quick-clean/apply", {
      method: "POST",
      body: JSON.stringify({ operations, preview_token: previewToken }),
    }),
  report: () => request<ChangeReport>("/api/report"),
  preview: (operation: Operation) =>
    request<OperationPreview>("/api/operations/preview", { method: "POST", body: JSON.stringify({ operation }) }),
  /** Operations that can remove data need the preview_token returned by preview(). */
  apply: (operation: Operation, previewToken?: string | null) =>
    request<ApplyResult>("/api/operations/apply", {
      method: "POST",
      body: JSON.stringify({ operation, preview_token: previewToken ?? undefined }),
    }),
  history: () => request<HistoryResponse>("/api/history"),
  undo: () => request<{ undone: HistoryItem; session: SessionInfo }>("/api/undo", { method: "POST" }),
  reset: () => request<{ steps_removed: number; session: SessionInfo }>("/api/reset", { method: "POST" }),
  compare: () => request<CompareResult>("/api/compare"),
  compareRows: (page: number, pageSize: number, changesOnly: boolean) =>
    request<CompareRowsPage>(`/api/compare/rows${qs({ page, page_size: pageSize, changes_only: changesOnly || undefined })}`),

  /** Downloads the current working dataset and returns the filename used. */
  async exportFile(filename: string, format: ExportFormat, bom: boolean, protectFormulas = false): Promise<string> {
    const sid = getSessionId();
    const response = await send(
      `${BASE}/api/export${qs({ filename, format, bom: format === "csv" ? bom : undefined, protect_formulas: format === "csv" && protectFormulas ? true : undefined })}`,
      { headers: sid ? { "X-Session-Id": sid } : {} },
      TIMEOUT_MS * 3, // Excel export of a large dataset can be slow
    );
    if (!response.ok) {
      const error = parseErrorBody(response.status, await response.json().catch(() => null));
      if (SESSION_GONE.has(error.code) && sid) window.dispatchEvent(new CustomEvent(SESSION_ENDED_EVENT));
      throw error;
    }
    const disposition = response.headers.get("content-disposition") ?? "";
    const match = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
    const name = match ? decodeURIComponent(match[1]) : `cleaned_data.${format}`;
    let blob: Blob;
    try {
      blob = await response.blob();
    } catch {
      throw new ApiError("The download was interrupted.", "download_failed", 0, "Try again.");
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return name;
  },
};
