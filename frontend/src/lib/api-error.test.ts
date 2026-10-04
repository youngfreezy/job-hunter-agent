import { describe, expect, it } from "vitest";
import { responseError } from "./api-error";

describe("API error explanations", () => {
  it("preserves actionable setup messages", async () => {
    expect(await responseError(new Response(JSON.stringify({detail: "Add your Anthropic key in Settings"}), {status: 403}), "Failed")).toBe("Add your Anthropic key in Settings");
  });
  it.each(["<html>Gateway unavailable</html>", JSON.stringify({detail: [{msg: "invalid"}]}), JSON.stringify({detail: " "})])("handles non-string and non-JSON errors safely", async body => {
    expect(await responseError(new Response(body, {status: 503}), "Please try again")).toBe("Please try again");
  });
});
