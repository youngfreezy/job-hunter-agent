import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

afterEach(() => vi.unstubAllGlobals());
describe("legacy Autopilot email navigation", () => {
  it("redirects to authenticated review without a token or paid request", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const id = "0e3df91d-92ce-47b1-9dbb-c37a6a3809ba";
    const response = await GET(new NextRequest(`https://jobhunteragent.com/api/autopilot/approve?schedule=fixture&session=${id}&token=fixture-secret&action=approve`));
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe(`/session/${id}`);
    expect(response.headers.get("Cache-Control")).toContain("no-store");
    expect(response.headers.get("Referrer-Policy")).toBe("no-referrer");
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each(["", "https://example.test", "../settings", "id?token=fixture", "//evil.test"])("rejects an invalid session path %s", async (id) => {
    const response = await GET(new NextRequest(`https://jobhunteragent.com/api/autopilot/approve?session=${encodeURIComponent(id)}`));
    expect(response.status).toBe(400);
    expect(response.headers.get("Location")).toBeNull();
  });
});
