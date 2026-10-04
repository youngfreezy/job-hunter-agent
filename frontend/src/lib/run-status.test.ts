import { describe, expect, it } from "vitest";
import { resolveRunStatus, restoreShortlistSelection } from "./run-status";

describe("authoritative approval gates", () => {
  it.each([["discovering", "awaiting_coach_review"], ["applying", "awaiting_review"]])("restores %s to its real %s gate", (current, next) => {
    expect(resolveRunStatus(current, next, "stream")).toBe(next);
    expect(resolveRunStatus(current, next, "snapshot", { coach: true, shortlist: true })).toBe(next);
  });
  it.each([["awaiting_coach_review", "discovering"], ["awaiting_review", "applying"]])("keeps unresolved %s open despite replayed %s", (current, next) => {
    expect(resolveRunStatus(current, next, "stream")).toBe(current);
    expect(resolveRunStatus(current, next, "snapshot")).toBe(current);
  });
  it("ignores old review events after an explicit approval", () => {
    expect(resolveRunStatus("discovering", "awaiting_coach_review", "stream", { coach: true })).toBe("discovering");
    expect(resolveRunStatus("applying", "awaiting_review", "stream", { shortlist: true })).toBe("applying");
  });
  it("ignores a still-old checkpoint while an acknowledged approval settles", () => {
    expect(resolveRunStatus("discovering", "awaiting_coach_review", "snapshot", { coach: true, settling: "awaiting_coach_review" })).toBe("discovering");
    expect(resolveRunStatus("applying", "awaiting_review", "snapshot", { shortlist: true, settling: "awaiting_review" })).toBe("applying");
  });
  it("preserves a deselection when the delayed shortlist GET arrives", () => {
    const initial = restoreShortlistSelection(new Set(), ["indeed", "employer"], false);
    initial.delete("employer");
    expect([...restoreShortlistSelection(initial, ["indeed", "employer"], true)]).toEqual(["indeed"]);
    expect([...restoreShortlistSelection(new Set(), ["indeed"], true)]).toEqual([]);
  });
  it("allows progress after approval and ignores backwards routine replay", () => {
    expect(resolveRunStatus("awaiting_coach_review", "discovering", "stream", { coach: true })).toBe("discovering");
    expect(resolveRunStatus("awaiting_review", "applying", "stream", { shortlist: true })).toBe("applying");
    expect(resolveRunStatus("applying", "discovering", "stream")).toBe("applying");
  });
  it.each(["completed", "failed"])("never reopens a %s run from a review replay or snapshot", (terminal) => {
    for (const source of ["stream", "snapshot"] as const) {
      expect(resolveRunStatus(terminal, "awaiting_coach_review", source)).toBe(terminal);
      expect(resolveRunStatus(terminal, "awaiting_review", source)).toBe(terminal);
      expect(resolveRunStatus("awaiting_review", terminal, source)).toBe(terminal);
    }
  });
});
