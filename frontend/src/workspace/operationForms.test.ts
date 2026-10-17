import type { ColumnProfile } from "@/api/types";
import { DEFAULT_FORM, buildOperation, columnRestriction, formForIssue } from "./operationForms";

const col = (name: string, type: ColumnProfile["type"], is_text = true): ColumnProfile => ({
  name,
  type,
  is_text,
  missing: 0,
  missing_pct: 0,
  completeness: 100,
  unique: 1,
});

describe("buildOperation", () => {
  it("requires columns for missing-value handling", () => {
    expect(buildOperation("missing_values", DEFAULT_FORM).error).toMatch(/column/);
  });

  it("requires a fill value for constant fill", () => {
    const f = { ...DEFAULT_FORM, mvColumns: ["a"], mvStrategy: "fill_constant" as const, mvValue: "" };
    expect(buildOperation("missing_values", f).error).toMatch(/value/);
    expect(buildOperation("missing_values", { ...f, mvValue: "0" }).operation).toEqual({
      type: "missing_values",
      strategy: "fill_constant",
      columns: ["a"],
      value: "0",
    });
  });

  it("does not send a value for drop strategies", () => {
    const op = buildOperation("missing_values", { ...DEFAULT_FORM, mvColumns: ["a"], mvStrategy: "drop_rows" }).operation;
    expect(op).toEqual({ type: "missing_values", strategy: "drop_rows", columns: ["a"] });
  });

  it("trims to all text columns by default", () => {
    expect(buildOperation("trim_whitespace", DEFAULT_FORM).operation).toEqual({ type: "trim_whitespace", columns: [] });
  });

  it("only sends a date format for datetime conversion", () => {
    const op = buildOperation("convert_type", { ...DEFAULT_FORM, convColumns: ["d"], convTarget: "integer", convFormat: "%d" }).operation;
    expect(op).toMatchObject({ date_format: null, dayfirst: false });
  });

  it("never builds an operation for outlier review", () => {
    expect(buildOperation("outliers", DEFAULT_FORM).operation).toBeUndefined();
  });
});

describe("column eligibility", () => {
  it("blocks non-numeric columns for mean and median", () => {
    const f = { ...DEFAULT_FORM, mvStrategy: "fill_mean" as const };
    expect(columnRestriction("missing_values", f, col("city", "text"))).toBe("Not numeric");
    expect(columnRestriction("missing_values", f, col("age", "integer"))).toBeNull();
  });

  it("blocks non-text columns for text operations", () => {
    expect(columnRestriction("standardize_text", DEFAULT_FORM, col("n", "integer", false))).toBe("Not text");
  });
});

describe("formForIssue", () => {
  it("prefills find & replace with the value the server reported, not a guess", () => {
    expect(formForIssue("find_replace", "city", "placeholder:city", [col("city", "text")], DEFAULT_FORM, "-").frFind).toBe("-");
    expect(formForIssue("find_replace", "city", "placeholder:city", [col("city", "text")], DEFAULT_FORM).frFind).toBe("");
  });
  it("prefills a numeric missing-value fix with the median", () => {
    const f = formForIssue("missing_values", "age", "missing:age", [col("age", "integer")], DEFAULT_FORM);
    expect(f.mvColumns).toEqual(["age"]);
    expect(f.mvStrategy).toBe("fill_median");
  });

  it("uses datetime conversion for date issues", () => {
    expect(formForIssue("convert_type", "d", "dates:d", [col("d", "text")], DEFAULT_FORM).convTarget).toBe("datetime");
  });
});
