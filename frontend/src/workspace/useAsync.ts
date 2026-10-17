import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/api/client";

type State<T> = { data: T | null; error: ApiError | null; loading: boolean };

/**
 * Run an async loader whenever `deps` change; ignores stale responses.
 *
 * While reloading, the previous result stays visible (dimmed) so paging and
 * sorting don't flicker — except when `dataVersion` changes: data from an
 * older version of the dataset is cleared immediately so it can never be
 * mistaken for the result of the latest cleaning step.
 */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[], dataVersion?: number) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true });
  const requestId = useRef(0);
  const [tick, setTick] = useState(0);
  const lastVersion = useRef(dataVersion);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(loader, deps);

  useEffect(() => {
    const id = ++requestId.current;
    const versionChanged = lastVersion.current !== dataVersion;
    lastVersion.current = dataVersion;
    setState((s) => ({ data: versionChanged ? null : s.data, error: null, loading: true }));
    run()
      .then((data) => {
        if (id === requestId.current) setState({ data, error: null, loading: false });
      })
      .catch((err: unknown) => {
        if (id !== requestId.current) return;
        const error = err instanceof ApiError ? err : new ApiError("Something went wrong.", "unexpected", 0, "Please try again.");
        setState((s) => ({ data: s.data, error, loading: false }));
      });
  }, [run, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

export function toApiError(err: unknown): ApiError {
  return err instanceof ApiError ? err : new ApiError("Something went wrong.", "unexpected", 0, "Please try again.");
}
