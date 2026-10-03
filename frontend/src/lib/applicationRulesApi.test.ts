import { afterEach, describe, expect, it, vi } from "vitest";
import { getApplicationRules, updateApplicationRules } from "./api";

afterEach(() => vi.unstubAllGlobals());
function mockRules(body: unknown, status = 200) {
  const fetch = vi.fn(async (url: string) => url === "/api/auth/token"
    ? new Response(JSON.stringify({}), { status: 200 })
    : new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("application rules API", () => {
  it("reads the dedicated rules endpoint, including legitimately empty rules", async () => {
    const fetch = mockRules({ application_rules: "" });
    expect(await getApplicationRules()).toBe("");
    expect(fetch.mock.calls.at(-1)?.[0]).toBe("/api/auth/me/application-rules");
  });
  it.each([{}, { application_rules: null }, { application_rules: [] }])("rejects missing or malformed rules without erasing existing settings: %j", async (body) => {
    mockRules(body);
    await expect(getApplicationRules()).rejects.toThrow("has not been saved");
  });
  it("rejects failed GET before callers can replace rules", async () => {
    mockRules({ detail: "Unauthorized" }, 401);
    await expect(getApplicationRules()).rejects.toThrow("has not been saved");
  });
  it("propagates failed PUT so the card retains its answer and shows no retry success", async () => {
    mockRules({ detail: "Unavailable" }, 503);
    await expect(updateApplicationRules("Existing rules plus answer")).rejects.toThrow("Failed to update");
  });
});
