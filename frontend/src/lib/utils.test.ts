import { fillLimits } from "./limits";
import { cn, formatBytes, formatCell, formatDelta, formatDuration, formatFromName, formatPercent, isSupportedFile, pluralize, suggestedOutputName } from "./utils";

describe("formatting helpers", () => {
  it("formats bytes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(10 * 1024 * 1024)).toBe("10.00 MB");
  });

  it("handles missing percentages safely", () => {
    expect(formatPercent(null)).toBe("N/A");
    expect(formatPercent(92.456)).toBe("92.5%");
  });

  it("formats signed deltas", () => {
    expect(formatDelta(5, 6)).toBe("−1");
    expect(formatDelta(8, 6)).toBe("+2");
    expect(formatDelta(6, 6)).toBe("0");
  });

  it("formats cells without float noise", () => {
    expect(formatCell(null)).toBe("");
    expect(formatCell(0.1 + 0.2)).toBe("0.3");
    expect(formatCell(42)).toBe("42");
    expect(formatCell("text")).toBe("text");
  });

  it("pluralizes", () => {
    expect(pluralize(1, "row")).toBe("1 row");
    expect(pluralize(1200, "row")).toBe("1,200 rows");
  });

  it("suggests an output name for every supported format", () => {
    expect(suggestedOutputName("Sales Data.CSV")).toBe("Sales Data_cleaned");
    expect(suggestedOutputName("book.xlsx")).toBe("book_cleaned");
    expect(suggestedOutputName("api.json")).toBe("api_cleaned");
  });

  it("recognises supported data files and rejects documents and images", () => {
    expect(formatFromName("x.csv")).toBe("csv");
    expect(formatFromName("x.TSV")).toBe("tsv");
    expect(formatFromName("x.xlsx")).toBe("xlsx");
    expect(formatFromName("x.xls")).toBe("xls");
    expect(formatFromName("x.jsonl")).toBe("json");
    expect(formatFromName("x.pdf")).toBeNull();
    expect(formatFromName("x.docx")).toBeNull();
    expect(formatFromName("photo.png")).toBeNull();
    expect(isSupportedFile(new File(["a"], "x.json"))).toBe(true);
  });

  it("formats durations", () => {
    expect(formatDuration(5.4)).toBe("5s");
    expect(formatDuration(95)).toBe("1m 35s");
  });
});

describe("cn", () => {
  it("keeps a type-scale size next to a text colour", () => {
    expect(cn("text-small font-medium", "text-muted-foreground")).toBe("text-small font-medium text-muted-foreground");
    expect(cn("text-small", "text-body")).toBe("text-body");
  });
});

describe("fillLimits", () => {
  it("uses the server's configured values", () => {
    expect(fillLimits("up to {limit}, kept {ttl}", { max_upload_mb: 25, session_ttl_minutes: 45 })).toBe("up to 25 MB, kept 45 minutes");
  });
  it("uses neutral wording when the server is unreachable", () => {
    expect(fillLimits("files up to {limit}; deleted after {ttl} of inactivity", null)).toBe(
      "files up to the server's size limit; deleted after a period of inactivity",
    );
  });
});
