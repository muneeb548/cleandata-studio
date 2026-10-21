import type { SessionInfo } from "@/api/types";
import { forgetWork, loadWork, saveWork, workKey } from "./savedWork";

const info = (steps: number, name = "sales.csv", size = 100): SessionInfo => ({
  file: { name, size, encoding: "utf-8", delimiter: ",", format: "csv", format_label: "CSV", sheet: null, sheets: [], warnings: [] },
  original_shape: { rows: 3, columns: 1 },
  current_shape: { rows: 3, columns: 1 },
  history: Array.from({ length: steps }, (_, i) => ({
    id: String(i),
    type: "trim_whitespace" as const,
    label: "Trim whitespace",
    params: { type: "trim_whitespace", columns: [] },
    summary: "",
    applied_at: 0,
    rows_before: 3,
    rows_after: 3,
    columns_before: 1,
    columns_after: 1,
    rows_removed: 0,
    columns_removed: 0,
    cells_changed: 0,
    warnings: [],
    undoable: true,
  })),
  log: [],
  can_undo: steps > 0,
  expires_in_seconds: 1800,
});

describe("continue where you left off", () => {
  beforeEach(() => localStorage.clear());

  it("saves only the steps and finds them again for the same file", () => {
    saveWork(info(2), 1000);
    const w = loadWork(info(0).file, 2000);
    expect(w?.steps).toEqual([{ type: "trim_whitespace", columns: [] }, { type: "trim_whitespace", columns: [] }]);
    expect(localStorage.getItem(workKey(info(0).file))).not.toContain("rows");
  });

  it("does not offer steps for a different file", () => {
    saveWork(info(2), 1000);
    expect(loadWork(info(0, "sales.csv", 101).file, 2000)).toBeNull();
    expect(loadWork(info(0, "other.csv").file, 2000)).toBeNull();
  });

  it("forgets when everything is undone, when asked, and after two weeks", () => {
    saveWork(info(1), 1000);
    saveWork(info(0), 1000);
    expect(loadWork(info(0).file, 2000)).toBeNull();
    saveWork(info(1), 1000);
    forgetWork(info(0).file);
    expect(loadWork(info(0).file, 2000)).toBeNull();
    saveWork(info(1), 1000);
    expect(loadWork(info(0).file, 1000 + 15 * 24 * 60 * 60 * 1000)).toBeNull();
  });

  it("ignores broken saved data", () => {
    localStorage.setItem(workKey(info(0).file), "{not json");
    expect(loadWork(info(0).file)).toBeNull();
  });
});
