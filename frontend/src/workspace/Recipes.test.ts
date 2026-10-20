import { parseRecipe } from "./Recipes";

describe("parseRecipe", () => {
  const recipe = {
    app: "CleanData Studio",
    kind: "cleaning-recipe",
    version: 1,
    name: "sales cleanup",
    source_file: "sales.csv",
    created_at: "2026-10-20T10:00:00+00:00",
    steps: [{ type: "trim_whitespace", columns: [] }],
  };

  it("reads a saved recipe", () => {
    expect(parseRecipe(JSON.stringify(recipe)).steps).toEqual([{ type: "trim_whitespace", columns: [] }]);
  });

  it("rejects files that are not recipes", () => {
    expect(() => parseRecipe("not json")).toThrow(/JSON/);
    expect(() => parseRecipe(JSON.stringify({ hello: 1 }))).toThrow(/not a CleanData Studio recipe/);
    expect(() => parseRecipe(JSON.stringify({ ...recipe, steps: [] }))).toThrow(/no steps/);
    expect(() => parseRecipe(JSON.stringify({ ...recipe, steps: [42] }))).toThrow(/unreadable/);
  });
});
