import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { encode } from "next-auth/jwt";
import { NextRequest } from "next/server";
import { GET } from "./route";

function request(cookie = "") {
  return new NextRequest("https://jobhunteragent.com/api/auth/token", { headers: { cookie } });
}

const secret = "test-only-session-secret-that-is-long-enough";
beforeEach(() => {
  vi.stubEnv("NEXTAUTH_SECRET", secret);
  vi.stubEnv("NEXTAUTH_URL", "https://jobhunteragent.com");
});
afterEach(() => vi.unstubAllEnvs());

describe("backend session token bridge", () => {
  it("reassembles a chunked OAuth session and prevents caching", async () => {
    const token = await encode({ secret, token: { sub: "user-1", profile: "x".repeat(5000) } });
    const cookie = `__Secure-next-auth.session-token.0=${token.slice(0, 3000)}; __Secure-next-auth.session-token.1=${token.slice(3000)}`;
    const response = await GET(request(cookie));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ token });
    expect(response.headers.get("Cache-Control")).toContain("no-store");
  });
  it("rejects an expired signed session", async () => {
    const token = await encode({ secret, maxAge: -60, token: { sub: "user-1" } });
    const response = await GET(request(`__Secure-next-auth.session-token=${token}`));
    expect(response.status).toBe(401);
  });
  it("rejects a missing session", async () => {
    expect((await GET(request())).status).toBe(401);
  });
});
