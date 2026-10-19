import type { ColumnProfile } from "@/api/types";
import { DEFAULT_FORM, buildOperation, columnRestriction, formForIssue, mappingRows } from "./operationForms";

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

describe("new cleaning operations", () => {
  it("builds a split with trimmed, distinct names", () => {
    expect(buildOperation("split_column", DEFAULT_FORM).error).toMatch(/column to split/);
    const f = { ...DEFAULT_FORM, splitColumn: "full_name", splitNames: [" first ", "last"] };
    expect(buildOperation("split_column", f).operation).toEqual({
      type: "split_column",
      column: "full_name",
      separator: " ",
      names: ["first", "last"],
      split_from: "start",
      keep_original: true,
    });
    expect(buildOperation("split_column", { ...f, splitNames: ["a", "a"] }).error).toMatch(/different/);
    expect(buildOperation("split_column", { ...f, splitNames: ["a", ""] }).error).toMatch(/name/);
  });

  it("only offers text columns for splitting", () => {
    expect(columnRestriction("split_column", DEFAULT_FORM, col("n", "integer", false))).toBe("Not text");
  });

  it("needs two columns and a name to merge", () => {
    expect(buildOperation("merge_columns", { ...DEFAULT_FORM, mergeColumns: ["a"] }).error).toMatch(/two/);
    expect(buildOperation("merge_columns", { ...DEFAULT_FORM, mergeColumns: ["a", "b"] }).error).toMatch(/name/);
    expect(buildOperation("merge_columns", { ...DEFAULT_FORM, mergeColumns: ["a", "b"], mergeName: " full " }).operation).toMatchObject({
      type: "merge_columns",
      new_name: "full",
      keep_originals: true,
    });
  });

  it("sends an upper-case country code for phones", () => {
    const op = buildOperation("standardize_phone", { ...DEFAULT_FORM, phoneColumns: ["p"], phoneRegion: "gb" }).operation;
    expect(op).toEqual({ type: "standardize_phone", columns: ["p"], region: "GB", region_column: null, format: "international", on_invalid: "keep" });
  });

  it("adds the region only to phone checks", () => {
    const f = {
      ...DEFAULT_FORM,
      flagRegion: "us",
      flagRules: [
        { column: "p", check: "invalid_phone" as const },
        { column: "e", check: "invalid_email" as const },
      ],
    };
    expect(buildOperation("flag_rows", f).operation).toEqual({
      type: "flag_rows",
      rules: [
        { column: "p", check: "invalid_phone", region: "US", region_column: null },
        { column: "e", check: "invalid_email" },
      ],
      column_name: "needs_review",
    });
    expect(buildOperation("flag_rows", DEFAULT_FORM).error).toMatch(/check/);
  });

  it("reads each row's country from a column when asked", () => {
    const f = { ...DEFAULT_FORM, phoneColumns: ["phone"], phoneRegionSource: "column" as const };
    expect(buildOperation("standardize_phone", f).error).toMatch(/country/);
    expect(buildOperation("standardize_phone", { ...f, phoneRegionColumn: "phone" }).error).toMatch(/cannot also/);
    expect(buildOperation("standardize_phone", { ...f, phoneRegionColumn: "country" }).operation).toMatchObject({ region_column: "country" });
  });

  it("builds country standardization", () => {
    expect(buildOperation("standardize_country", DEFAULT_FORM).error).toMatch(/column/);
    expect(buildOperation("standardize_country", { ...DEFAULT_FORM, countryColumns: ["c"], countryOutput: "code" }).operation).toEqual({
      type: "standardize_country",
      columns: ["c"],
      output: "code",
    });
  });
});

describe("emails, amounts and value mapping", () => {
  it("builds email cleanup with safe defaults", () => {
    expect(buildOperation("clean_email", DEFAULT_FORM).error).toMatch(/column/);
    expect(buildOperation("clean_email", { ...DEFAULT_FORM, emailColumns: ["e"] }).operation).toEqual({
      type: "clean_email",
      columns: ["e"],
      lowercase: true,
      fix_domains: false,
      on_invalid: "keep",
    });
  });

  it("builds number cleanup that stops on bad values by default", () => {
    expect(buildOperation("clean_numbers", { ...DEFAULT_FORM, numColumns: ["amount"] }).operation).toEqual({
      type: "clean_numbers",
      columns: ["amount"],
      decimal: "auto",
      on_error: "abort",
    });
  });

  it("only sends mapping rows that change something", () => {
    expect(mappingRows({ a: "", b: "b", c: " C ", d: "  " })).toEqual([{ value: "c", to: "C" }]);
    expect(buildOperation("map_values", { ...DEFAULT_FORM, mapColumn: "city" }).error).toMatch(/new value/);
    expect(buildOperation("map_values", { ...DEFAULT_FORM, mapColumn: "city", mapEdits: { isb: "Islamabad" } }).operation).toEqual({
      type: "map_values",
      columns: ["city"],
      mappings: [{ value: "isb", to: "Islamabad" }],
      ignore_case: true,
    });
  });
});

describe("near-duplicates", () => {
  it("flags by default and needs the identifying columns", () => {
    expect(buildOperation("near_duplicates", DEFAULT_FORM).error).toMatch(/columns/);
    expect(buildOperation("near_duplicates", { ...DEFAULT_FORM, ndColumns: ["name", "email"] }).operation).toEqual({
      type: "near_duplicates",
      columns: ["name", "email"],
      match: "normalized",
      action: "flag",
      column_name: "duplicate_group",
    });
  });
});
