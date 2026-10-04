import { describe, expect, it } from "vitest";
import { applicationLogStatus, applicationLogLabel } from "./application-log";
describe("application log delivery status", () => {
  it("separates uncertain delivery from failures eligible for a manual retry", () => {
    const pending = { status: "failed" as const, error_category: "submission_uncertain" };
    expect(applicationLogStatus(pending)).toBe("uncertain");
    expect(applicationLogLabel(pending)).toBe("Confirmation pending—check before retrying");
  });
  it("preserves confirmed submissions and ordinary failures", () => {
    expect(applicationLogStatus({status: "submitted"})).toBe("submitted");
    expect(applicationLogStatus({status: "failed", error_category: "validation"})).toBe("failed");
  });
});
