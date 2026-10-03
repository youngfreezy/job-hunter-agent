import { describe, expect, it } from "vitest";
import { buildLedger, formatElapsed, runName, runOutcome, scoreThreshold, shouldRefreshSession } from "./run";

describe("runName", () => {
  it("names a run by its first role, the count of others and the place", () => {
    expect(runName({ keywords: ["Applied AI Engineer", "ML Engineer", "LLM Engineer"], locations: ["San Francisco"] })).toBe(
      "Applied AI Engineer +2 · San Francisco"
    );
    expect(runName({ keywords: ["Platform Engineer"], locations: [], remote_only: true })).toBe("Platform Engineer · Remote");
  });
});

describe("runOutcome", () => {
  it("never reports a run that sent nothing as success", () => {
    expect(runOutcome({ status: "completed", submitted: 0, failed: 0 })).toEqual({
      tone: "neutral",
      label: "Finished · nothing sent",
    });
    expect(runOutcome({ status: "completed", submitted: 0, failed: 2 }).tone).toBe("failed");
    expect(runOutcome({ status: "completed", submitted: 4, failed: 0 })).toEqual({ tone: "sent", label: "Finished · 4 sent" });
  });

  it("flags open gates as needing the user", () => {
    expect(runOutcome({ status: "awaiting_review" }).tone).toBe("needs");
  });
});

describe("buildLedger", () => {
  it("draws a finished run with an empty shortlist as hollow from the shortlist on, with a reason", () => {
    const { phases, gates } = buildLedger({
      status: "completed",
      coachScore: 82,
      found: 43,
      shortlisted: 0,
      submitted: 0,
      failed: 0,
      threshold: 50,
    });
    expect(phases.map((p) => p.state)).toEqual(["done", "done", "empty", "empty", "empty"]);
    expect(phases.map((p) => p.count)).toEqual([82, 43, 0, 0, 0]);
    expect(phases[2].reason).toBe("0 of 43 scored 50 or higher");
    expect(gates).toEqual({ coach: "passed", shortlist: "todo" });
  });

  it("counts explicit Quick Apply links even before scoring state arrives", () => {
    const { phases, gates } = buildLedger({
      status: "applying", found: 2, shortlisted: 0, attempted: 1,
      selectedJobUrls: ["https://indeed.com/a", "https://indeed.com/b", "https://indeed.com/a"],
    });
    expect(phases[2]).toMatchObject({ label: "Selected jobs", count: 2, state: "done" });
    expect(phases[2].reason).toBeUndefined();
    expect(gates.shortlist).toBe("passed");
  });

  it("opens the shortlist gate while waiting for approval", () => {
    const { phases, gates } = buildLedger({ status: "awaiting_review", found: 58, shortlisted: 6 });
    expect(gates.shortlist).toBe("open");
    expect(phases[2].state).toBe("current");
    expect(phases[3].state).toBe("todo");
  });

  it("leaves unknown counts empty instead of inventing them", () => {
    const { phases } = buildLedger({ status: "discovering" });
    expect(phases.map((p) => p.count)).toEqual([null, null, null, null, null]);
  });
});

describe("scoreThreshold and formatElapsed", () => {
  it("matches the backend cutoff of 30 + strictness × 40", () => {
    expect(scoreThreshold({ scoring_strictness: 0.5 })).toBe(50);
    expect(scoreThreshold({ scoring_strictness: 1 })).toBe(70);
    expect(scoreThreshold({ discovery_mode: "manual_urls" })).toBeNull();
  });
  it("formats time since start", () => {
    expect(formatElapsed(161)).toBe("+2:41");
    expect(formatElapsed(3725)).toBe("+1:02:05");
  });
});


// Sparse outcome events must reload authoritative totals instead of incrementing
// local counters; replaying them therefore cannot count an application twice.
describe("durable application totals", () => {
  it("refreshes sparse results and a circuit-breaker shortlist", () => {
    for (const event of ["application_start", "application_failed", "application_submitted", "shortlist_review"]) {
      expect(shouldRefreshSession({ event })).toBe(true);
    }
  });
  it("keeps routine progress local and refreshes terminal status", () => {
    expect(shouldRefreshSession({ event: "application_progress" })).toBe(false);
    expect(shouldRefreshSession({ event: "status", status: "failed" })).toBe(true);
    expect(shouldRefreshSession({ event: "status", status: "applying" })).toBe(false);
  });
});
