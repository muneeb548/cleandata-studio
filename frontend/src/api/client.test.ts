import { ApiError, SESSION_GONE, parseErrorBody, timeoutError } from "./client";

describe("parseErrorBody", () => {
  it("uses the server's message and hint", () => {
    const err = parseErrorBody(400, { error: { code: "empty_file", message: "The file is empty.", hint: "Try again." } });
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe("The file is empty.");
    expect(err.hint).toBe("Try again.");
    expect(err.code).toBe("empty_file");
  });

  it("explains network failures", () => {
    expect(parseErrorBody(0, null).code).toBe("network_error");
  });

  it("never shows raw server output", () => {
    const err = parseErrorBody(500, "<html>Traceback ...</html>");
    expect(err.message).not.toContain("Traceback");
  });

  it("maps rate limits, unavailable servers and timeouts to helpful messages", () => {
    expect(parseErrorBody(429, null).code).toBe("rate_limited");
    expect(parseErrorBody(503, null).code).toBe("unavailable");
    expect(timeoutError().code).toBe("timeout");
  });

  it("recognises expired sessions", () => {
    expect(SESSION_GONE.has(parseErrorBody(404, { error: { code: "session_expired", message: "x" } }).code)).toBe(true);
    expect(SESSION_GONE.has("preview_outdated")).toBe(false);
  });
});
