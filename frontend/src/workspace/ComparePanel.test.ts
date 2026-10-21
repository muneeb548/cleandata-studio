import type { Stats } from "@/api/types";
import { withQuality } from "./ComparePanel";

const stats: Stats = {
  rows: 12,
  columns: 8,
  total_cells: 96,
  missing_cells: 0,
  duplicate_rows: 1,
  columns_with_missing: 0,
  completeness: 100,
  empty_rows: 0,
  empty_columns: 0,
};

describe("withQuality", () => {
  it('counts "N/A"-style cells as missing, so cleaning them does not look like a step back', () => {
    const before = withQuality(stats, { missing_cells: 4, columns_with_missing: 2, completeness: 95.8, problems: 12 });
    expect(before.missing_cells).toBe(4);
    expect(before.completeness).toBe(95.8);
    expect(before.problems).toBe(12);
    expect(before.duplicate_rows).toBe(1);
  });

  it("falls back to the plain numbers from an older server", () => {
    expect(withQuality(stats).missing_cells).toBe(0);
    expect(withQuality(stats).problems).toBeUndefined();
  });
});
