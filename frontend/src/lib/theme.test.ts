// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { describe, expect, it } from "vitest";
import { nextThemePreference, parseThemePreference, resolveDark } from "./theme";

describe("theme preference", () => {
  it("defaults unknown or missing values to system", () => {
    expect(parseThemePreference(null)).toBe("system");
    expect(parseThemePreference("purple")).toBe("system");
    expect(parseThemePreference("light")).toBe("light");
    expect(parseThemePreference("dark")).toBe("dark");
  });

  it("cycles system -> light -> dark -> system", () => {
    expect(nextThemePreference("system")).toBe("light");
    expect(nextThemePreference("light")).toBe("dark");
    expect(nextThemePreference("dark")).toBe("system");
  });

  it("lets an explicit choice override the OS setting", () => {
    expect(resolveDark("light", true)).toBe(false);
    expect(resolveDark("dark", false)).toBe(true);
    expect(resolveDark("system", true)).toBe(true);
    expect(resolveDark("system", false)).toBe(false);
  });
});
