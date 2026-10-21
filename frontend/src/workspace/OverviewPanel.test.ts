import type { Issue } from "@/api/types";
import { problemTitles } from "./OverviewPanel";

const issue = (title: string, column: string | null, severity: Issue["severity"] = "low"): Issue => ({
  id: title,
  severity,
  title,
  description: "",
  column,
  count: 1,
  suggested_operation: null,
});

describe("problemTitles", () => {
  it("lists the column's problems without repeating the column name, and skips notes", () => {
    const issues = [
      issue('Mixed date formats in "order_date"', "order_date", "medium"),
      issue('Possible outliers in "order_date"', "order_date", "info"),
      issue('Inconsistent capitalisation in "city"', "city"),
      issue("1 duplicate row", null),
    ];
    expect(problemTitles(issues, "order_date")).toEqual(["Mixed date formats"]);
    expect(problemTitles(issues, "city")).toEqual(["Inconsistent capitalisation"]);
    expect(problemTitles(issues, "email")).toEqual([]);
  });
});
