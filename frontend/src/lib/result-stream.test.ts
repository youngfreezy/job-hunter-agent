import { describe, expect, it } from "vitest";
import { resultStreamError } from "./result-stream";

describe("result stream errors", () => {
  it("explains a transport or authorization failure", () => {
    expect(resultStreamError(new Event("error"))).toContain("result connection");
  });
  it("preserves an actionable backend message", () => {
    expect(resultStreamError(new MessageEvent("error", { data: JSON.stringify({ message: "Add your provider key in Settings." }) }))).toBe("Add your provider key in Settings.");
  });
  it.each(["bad-json", "null", '{"message":3}', '{"message":"  "}'])("does not lose recovery for malformed data %s", (data) => {
    expect(resultStreamError(new MessageEvent("error", { data }))).toContain("reconnect");
  });
});
