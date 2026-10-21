import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, getSessionId, SESSION_ENDED_EVENT, SESSION_GONE, setSessionId } from "@/api/client";
import type { AppConfig, OperationType, SessionInfo, UploadResponse } from "@/api/types";
import { useToast } from "@/components/ui/toast";
import { loadWork, forgetWork, saveWork, type SavedWork } from "./savedWork";
import { toApiError } from "./useAsync";

export type Tab = "overview" | "data" | "clean" | "compare" | "export";

/** A cleaning operation requested from somewhere else (e.g. the "Fix" button on an issue). */
export type OperationRequest = { type: OperationType | "outliers"; column?: string | null; issueId?: string; example?: string | null; nonce: number };

type WorkspaceState = {
  status: "loading" | "empty" | "ready";
  /** Server limits from /api/config (null until loaded or if the server is unreachable). */
  config: AppConfig | null;
  /** Why the user is back on the upload screen (e.g. the session expired). */
  notice: string | null;
  info: SessionInfo | null;
  /** Increments whenever the working dataset changes, so panels refetch. */
  version: number;
  tab: Tab;
  setTab: (tab: Tab) => void;
  request: OperationRequest | null;
  openOperation: (type: OperationRequest["type"], column?: string | null, issueId?: string, example?: string | null) => void;
  onUploaded: (res: UploadResponse) => void;
  onSessionChanged: (info: SessionInfo) => void;
  /** Which history action is running; buttons use it for loading/disabled states. */
  pending: "undo" | "reset" | null;
  undo: () => Promise<void>;
  reset: () => Promise<void>;
  startOver: () => Promise<void>;
  /** Deletes the session from the server right now. Resolves true only when the data is really gone. */
  deleteData: () => Promise<boolean>;
  handleError: (err: unknown, title?: string) => void;
  /** Steps saved in this browser for the file just uploaded, offered as "continue where you left off". */
  resume: SavedWork | null;
  /** Hides the offer; with forget=true the saved steps are removed too. */
  dismissResume: (forget: boolean) => void;
};

const Ctx = createContext<WorkspaceState | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const toast = useToast();
  const [status, setStatus] = useState<WorkspaceState["status"]>(getSessionId() ? "loading" : "empty");
  const [info, setInfo] = useState<SessionInfo | null>(null);
  const [version, setVersion] = useState(0);
  const [tab, setTab] = useState<Tab>("overview");
  const [request, setRequest] = useState<OperationRequest | null>(null);
  const [pending, setPending] = useState<"undo" | "reset" | null>(null);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [resume, setResume] = useState<SavedWork | null>(null);

  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
  }, []);
  // A ref (not state) so a fast double-click can't start two requests before React re-renders.
  const inFlight = useRef(false);

  const clearSession = useCallback((why: string | null = null) => {
    setSessionId(null);
    setInfo(null);
    setResume(null);
    setNotice(why);
    setStatus("empty");
    setTab("overview");
  }, []);

  const handleError = useCallback(
    (err: unknown, title?: string) => {
      const e = toApiError(err);
      if (SESSION_GONE.has(e.code)) {
        clearSession("Your previous session has ended — for privacy, data is deleted after a period of inactivity or when the server restarts. Please upload the file again.");
        toast({ tone: "info", title: "Your session has ended", description: "For privacy, data is deleted after inactivity. Please upload the file again." });
        return;
      }
      toast({ tone: "error", title: title ?? e.message, description: title ? `${e.message}${e.hint ? ` ${e.hint}` : ""}` : (e.hint ?? undefined) });
    },
    [clearSession, toast],
  );

  // Any request (overview, table, compare, download…) that finds the session gone
  // returns the user to the upload screen with an explanation, instead of a dead page.
  useEffect(() => {
    const onEnded = () =>
      clearSession("Your session has ended — for privacy, data is deleted after a period of inactivity or when the server restarts. Please upload the file again.");
    window.addEventListener(SESSION_ENDED_EVENT, onEnded);
    return () => window.removeEventListener(SESSION_ENDED_EVENT, onEnded);
  }, [clearSession]);

  // Restore a session after a page refresh.
  useEffect(() => {
    if (!getSessionId()) return;
    api
      .session()
      .then((s) => {
        setInfo(s);
        setStatus("ready");
      })
      .catch((err) =>
        clearSession(
          SESSION_GONE.has((err as { code?: string }).code ?? "")
            ? "Your previous session has ended (expired or the server restarted). Please upload the file again."
            : "Could not restore your previous session. Please upload the file again.",
        ),
      );
  }, [clearSession]);

  // Remember the applied steps in this browser so tomorrow's upload of the same file can continue.
  // Not while an offer to continue is open, or the old steps would be overwritten before the user decides.
  useEffect(() => {
    if (info && !resume) saveWork(info);
  }, [info, resume]);

  const dismissResume = useCallback(
    (forget: boolean) => {
      if (forget && info) forgetWork(info.file);
      setResume(null);
    },
    [info],
  );

  const onSessionChanged = useCallback((next: SessionInfo) => {
    setResume(null); // the user changed the data, so they chose to carry on from here
    setInfo(next);
    setVersion((v) => v + 1);
  }, []);

  const onUploaded = useCallback((res: UploadResponse) => {
    setSessionId(res.session_id);
    const { session_id: _ignored, ...rest } = res;
    void _ignored;
    setInfo(rest);
    setResume(rest.history.length ? null : loadWork(rest.file));
    setNotice(null);
    setVersion((v) => v + 1);
    setStatus("ready");
    setTab("overview");
  }, []);

  const runHistoryAction = useCallback(
    async (kind: "undo" | "reset") => {
      if (inFlight.current) return;
      inFlight.current = true;
      setPending(kind);
      try {
        const res = kind === "undo" ? await api.undo() : await api.reset();
        onSessionChanged(res.session);
        toast(
          kind === "undo"
            ? { tone: "success", title: "Last operation undone", description: "undone" in res && res.undone ? `Reverted: ${res.undone.label}` : undefined }
            : { tone: "success", title: "Dataset reset to the original upload", description: "All applied operations were removed." },
        );
      } catch (err) {
        handleError(err, kind === "undo" ? "Could not undo" : "Could not reset");
        // Re-sync with the server so the buttons reflect the real history.
        api.session().then(onSessionChanged).catch(() => undefined);
      } finally {
        inFlight.current = false;
        setPending(null);
      }
    },
    [handleError, onSessionChanged, toast],
  );

  const undo = useCallback(() => runHistoryAction("undo"), [runHistoryAction]);
  const reset = useCallback(() => runHistoryAction("reset"), [runHistoryAction]);

  const startOver = useCallback(async () => {
    try {
      await api.endSession();
    } catch {
      /* the session may already be gone; nothing else to do */
    }
    clearSession(null);
  }, [clearSession]);

  const deleteData = useCallback(async () => {
    try {
      await api.endSession();
    } catch (err) {
      // "Session not found" means it is already gone, which is what the user wants.
      if (!SESSION_GONE.has(toApiError(err).code)) {
        handleError(err, "Could not delete the data");
        return false;
      }
    }
    if (info) forgetWork(info.file); // finished with this file: also forget its saved steps in this browser
    clearSession("Your file, the cleaned data and the cleaning history were deleted from the server.");
    toast({ tone: "success", title: "Data deleted", description: "Nothing from this file is kept on the server." });
    return true;
  }, [clearSession, handleError, info, toast]);

  const openOperation = useCallback((type: OperationRequest["type"], column?: string | null, issueId?: string, example?: string | null) => {
    setRequest({ type, column, issueId, example, nonce: Date.now() });
    setTab("clean");
  }, []);

  const value = useMemo(
    () => ({ status, config, notice, info, version, tab, setTab, request, openOperation, onUploaded, onSessionChanged, pending, undo, reset, startOver, deleteData, handleError, resume, dismissResume }),
    [status, config, notice, info, version, tab, request, openOperation, onUploaded, onSessionChanged, pending, undo, reset, startOver, deleteData, handleError, resume, dismissResume],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWorkspace() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useWorkspace must be used inside <WorkspaceProvider>");
  return ctx;
}
