/**
 * "Continue where you left off".
 *
 * The server deletes a session after a period of inactivity, so the data itself is never
 * kept. What this file keeps is only the list of applied steps (the same thing a recipe
 * contains), in this browser's localStorage, keyed by the file's name, sheet and size.
 * When the same file is uploaded again, the workspace offers to replay those steps.
 */
import type { Operation, SessionInfo } from "@/api/types";

const PREFIX = "cds:work:";
const MAX_SAVED = 20;
const MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000; // forget after two weeks

export type SavedWork = { file: string; savedAt: number; steps: Operation[] };

type FileId = Pick<SessionInfo["file"], "name" | "size" | "sheet">;

export const workKey = (file: FileId) => `${PREFIX}${file.name}|${file.sheet ?? ""}|${file.size}`;

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null; // private mode or blocked storage: the feature simply turns off
  }
}

function allKeys(store: Storage): string[] {
  const keys: string[] = [];
  for (let i = 0; i < store.length; i++) {
    const k = store.key(i);
    if (k?.startsWith(PREFIX)) keys.push(k);
  }
  return keys;
}

function read(store: Storage, key: string): SavedWork | null {
  try {
    const raw = store.getItem(key);
    if (!raw) return null;
    const w = JSON.parse(raw) as Partial<SavedWork>;
    if (typeof w.savedAt !== "number" || !Array.isArray(w.steps) || !w.steps.length) return null;
    if (!w.steps.every((s) => s && typeof s === "object" && typeof (s as { type?: unknown }).type === "string")) return null;
    return { file: String(w.file ?? ""), savedAt: w.savedAt, steps: w.steps as Operation[] };
  } catch {
    return null;
  }
}

/** Saves the steps applied so far (or forgets them when there are none). */
export function saveWork(info: SessionInfo, now = Date.now()): void {
  const store = storage();
  if (!store) return;
  const key = workKey(info.file);
  try {
    if (!info.history.length) {
      store.removeItem(key);
      return;
    }
    const steps = info.history.map((h) => h.params as unknown as Operation);
    store.setItem(key, JSON.stringify({ file: info.file.name, savedAt: now, steps } satisfies SavedWork));
    // Keep only the most recent files.
    const others = allKeys(store)
      .map((k) => ({ k, w: read(store, k) }))
      .sort((a, b) => (b.w?.savedAt ?? 0) - (a.w?.savedAt ?? 0));
    others.slice(MAX_SAVED).forEach(({ k }) => store.removeItem(k));
  } catch {
    /* storage full or blocked: not worth interrupting the user */
  }
}

/** Steps saved earlier for this exact file, if any and not too old. */
export function loadWork(file: FileId, now = Date.now()): SavedWork | null {
  const store = storage();
  if (!store) return null;
  const key = workKey(file);
  const w = read(store, key);
  if (w && now - w.savedAt > MAX_AGE_MS) {
    forgetWork(file);
    return null;
  }
  return w;
}

export function forgetWork(file: FileId): void {
  try {
    storage()?.removeItem(workKey(file));
  } catch {
    /* ignore */
  }
}
