import { describe, expect, it } from "vitest";
import { safeAuthCallback } from "./auth-navigation";

describe("authentication return destination", () => {
  it("preserves a protected deep link and query", () => {
    expect(safeAuthCallback("/session/new?mode=quick", "https://jobhunteragent.com", "/dashboard"))
      .toBe("/session/new?mode=quick");
    expect(safeAuthCallback("https://jobhunteragent.com/settings", "https://jobhunteragent.com", "/dashboard"))
      .toBe("/settings");
  });
  it.each(["https://evil.example/", "//evil.example/", "/\\evil.example/", "javascript:alert(1)", "/auth/login", "/api/auth/signout", "/auth/signup?callbackUrl=/auth/login"])("rejects unsafe or looping destination %s", (value) => {
    expect(safeAuthCallback(value, "https://jobhunteragent.com", "/dashboard")).toBe("/dashboard");
  });
  it("supports the local origin and a signup fallback", () => {
    expect(safeAuthCallback("http://localhost:3000/session/new", "http://localhost:3000", "/dashboard"))
      .toBe("/session/new");
    expect(safeAuthCallback(null, "https://jobhunteragent.com", "/session/new")).toBe("/session/new");
  });
});
