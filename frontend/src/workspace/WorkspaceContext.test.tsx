import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { SessionInfo } from "@/api/types";
import { ToastProvider } from "@/components/ui/toast";
import { WorkspaceProvider, useWorkspace } from "./WorkspaceContext";

const session = (history: number): SessionInfo => ({
  file: { name: "a.csv", size: 10, encoding: "utf-8", delimiter: ",", format: "csv", format_label: "CSV", sheet: null, sheets: [], warnings: [] },
  original_shape: { rows: 3, columns: 1 },
  current_shape: { rows: 3 - history, columns: 1 },
  history: Array.from({ length: history }, (_, i) => ({
    id: String(i),
    type: "remove_duplicates" as const,
    label: "Remove duplicate rows",
    params: {},
    summary: "Removed 1 row",
    applied_at: 0,
    rows_before: 3,
    rows_after: 2,
    columns_before: 1,
    columns_after: 1,
    rows_removed: 1,
    columns_removed: 0,
    cells_changed: 0,
    warnings: [],
    undoable: true,
  })),
  log: [],
  can_undo: history > 0,
  expires_in_seconds: 1800,
});

let resolveUndo: (v: unknown) => void = () => undefined;
const undo = vi.fn(() => new Promise((r) => (resolveUndo = r)));
const reset = vi.fn(async () => ({ session: session(0) }));
const endSession = vi.fn(async () => null);

vi.mock("@/api/client", async (orig) => {
  const actual = await orig<typeof import("@/api/client")>();
  return {
    ...actual,
    getSessionId: () => "sid",
    api: { ...actual.api, session: vi.fn(async () => session(2)), undo: () => undo(), reset: () => reset(), endSession: () => endSession() },
  };
});

function Probe() {
  const ws = useWorkspace();
  return (
    <div>
      <p data-testid="history">{ws.info?.history.length ?? "none"}</p>
      <p data-testid="version">{ws.version}</p>
      <p data-testid="pending">{ws.pending ?? "idle"}</p>
      <button onClick={() => void ws.undo()}>undo</button>
      <button onClick={() => void ws.reset()}>reset</button>
      <button onClick={() => void ws.deleteData()}>delete</button>
      <p data-testid="notice">{ws.notice ?? ""}</p>
    </div>
  );
}

function setup() {
  render(
    <ToastProvider>
      <WorkspaceProvider>
        <Probe />
      </WorkspaceProvider>
    </ToastProvider>,
  );
}

describe("Undo and Reset", () => {
  beforeEach(() => {
    undo.mockClear();
    reset.mockClear();
  });

  it("sends only one undo request on a double click and updates the data afterwards", async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId("history")).toHaveTextContent("2"));
    const version = Number(screen.getByTestId("version").textContent);
    await userEvent.dblClick(screen.getByText("undo"));
    expect(undo).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("pending")).toHaveTextContent("undo");
    await act(async () => resolveUndo({ undone: session(2).history[1], session: session(1) }));
    await waitFor(() => expect(screen.getByTestId("pending")).toHaveTextContent("idle"));
    expect(screen.getByTestId("history")).toHaveTextContent("1");
    expect(Number(screen.getByTestId("version").textContent)).toBe(version + 1);
    expect(await screen.findByText("Last operation undone")).toBeInTheDocument();
  });

  it("reset clears the history and bumps the data version", async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId("history")).toHaveTextContent("2"));
    await userEvent.click(screen.getByText("reset"));
    await waitFor(() => expect(screen.getByTestId("history")).toHaveTextContent("0"));
    expect(reset).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Dataset reset to the original upload")).toBeInTheDocument();
  });
});

describe("Delete my data now", () => {
  it("deletes the session on the server and returns to the upload screen", async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId("history")).toHaveTextContent("2"));
    await userEvent.click(screen.getByText("delete"));
    expect(endSession).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByTestId("history")).toHaveTextContent("none"));
    expect(screen.getByTestId("notice")).toHaveTextContent("deleted from the server");
  });
});
