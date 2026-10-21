import { parseRecipe, recipeCardText, recipeCounts } from "./Recipes";

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

describe("recipe card", () => {
  it("does not count Combine files steps", () => {
    expect(recipeCounts([{ type: "combine_files" }])).toEqual({ saveable: 0, leftOut: 1 });
    expect(recipeCounts([{ type: "trim_whitespace" }, { type: "combine_files" }, { type: "sort_rows" }])).toEqual({ saveable: 2, leftOut: 1 });
  });

  it("explains what is saved", () => {
    expect(recipeCardText(0, 0)).toMatch(/^Save the steps you applied/);
    expect(recipeCardText(2, 0)).toMatch(/^Save the 2 steps you applied/);
    expect(recipeCardText(0, 0)).not.toMatch(/Combine/);
    expect(recipeCardText(1, 1)).toMatch(/Save the 1 step you applied.*1 Combine files step is not saved/);
    expect(recipeCardText(1, 2)).toMatch(/2 Combine files steps are not saved/);
    expect(recipeCardText(0, 1)).toMatch(/^Combine files steps cannot be saved/);
  });
});
