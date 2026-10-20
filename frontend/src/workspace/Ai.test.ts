import { describe, expect, it } from "vitest";
import { AI_EXAMPLES, mergeSuggestions } from "./Ai";

describe("mergeSuggestions", () => {
  it("fills empty rows and never overwrites what the user typed", () => {
    const { edits, added } = mergeSuggestions(
      { Lhr: "Lahore City", Karachi: "" },
      [
        { value: "Lhr", to: "Lahore" },
        { value: "LAHORE", to: "Lahore" },
        { value: "Karachi", to: "Karachi" },
      ],
    );
    expect(edits).toEqual({ Lhr: "Lahore City", LAHORE: "Lahore", Karachi: "Karachi" });
    expect(added).toBe(2);
  });

  it("does not change the original object", () => {
    const original = { a: "" };
    mergeSuggestions(original, [{ value: "a", to: "A" }]);
    expect(original).toEqual({ a: "" });
  });

  it("has example requests", () => {
    expect(AI_EXAMPLES.length).toBeGreaterThan(0);
  });
});

describe("QUESTION_EXAMPLES", () => {
  it("are long enough to be sent", async () => {
    const { QUESTION_EXAMPLES } = await import("./Ai");
    expect(QUESTION_EXAMPLES.every((q) => q.trim().length >= 3)).toBe(true);
  });
});
