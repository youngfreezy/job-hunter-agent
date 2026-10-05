import { describe, expect, it } from "vitest";
import { compressEvents } from "./event-log";
import { sessionPresentation } from "./presentation";
import { applySessionEvent } from "./session-events";
import type { SessionData, SSEEvent } from "./types";

function session(overrides: Partial<SessionData> = {}): SessionData {
  return {
    session_id: "run-1", status: "applying", keywords: ["Engineer"],
    applications_submitted: [], applications_failed: [], scored_jobs: [],
    applications_used: 0, applications_skipped: 0,
    created_at: "2026-10-05T10:00:00Z", ...overrides,
  };
}

describe("session presentation", () => {
  it("keeps uncertainty visible without claiming no applications were sent", () => {
    const view = sessionPresentation(session({ status: "failed", applications_failed: [{ error_category: "submission_uncertain" }] }), null, [], [], 0, false);
    expect(view.stateLine).toBe("Stopped · Confirmation pending—check before retrying");
    expect(view.stateTone).toBe("needs");
    expect(view.failedCount).toBe(0);
    expect(view.uncertainCount).toBe(1);
  });

  it("keeps an approved interrupted run distinct from zero attempts", () => {
    const view = sessionPresentation(session({ status: "failed", application_queue: ["job-1"] }), null, [], [], 0, false);
    expect(view.stateLine).toContain("no submission confirmed");
    expect(view.ledger.phases.find(phase => phase.key === "apply")?.count).toBeNull();
  });

  it("uses Quick Apply URLs without inventing score requirements", () => {
    const data = session({ session_config: { discovery_mode: "manual_urls", job_urls: ["https://indeed.com/a", "https://indeed.com/b"] } });
    const view = sessionPresentation(data, null, [], [], 65, false);
    expect(view.shortlisted).toBe(2);
    expect(view.threshold).toBeNull();
    expect(view.stateLine).toContain("1:05");
    expect(view.ledger.gates.shortlist).toBe("passed");
  });

  it("groups compressed events, retaining the newest timestamp and source input", () => {
    const events: SSEEvent[] = [
      { event: "discovery_progress", step: "Searching", timestamp: "2026-10-05T10:00:01Z", jobs_found: 2 },
      { event: "discovery_progress", step: "Searching", timestamp: "2026-10-05T10:00:05Z", jobs_found: 4 },
      { event: "error", message: "Try again", timestamp: "2026-10-05T10:00:06Z" },
    ];
    const before = JSON.stringify(events);
    const view = sessionPresentation(session(), null, events, [], 0, false);
    expect(view.found).toBe(4);
    expect(view.logRows).toHaveLength(2);
    expect(view.logRows[0]).toMatchObject({ group: "search", t: "+0:05" });
    expect(view.logRows[1]).toMatchObject({ group: "search", tone: "error" });
    expect(JSON.stringify(events)).toBe(before);
  });

  it("bounds the visible activity history to the last 50 distinct events", () => {
    const events = Array.from({ length: 60 }, (_, index) => ({ event: "note", message: `Step ${index}` }));
    expect(compressEvents(events)).toEqual(events.slice(10));
  });
});

describe("session event reduction", () => {
  it("does not erase cumulative totals for a step-only progress event", () => {
    const previous = session({ applications_submitted: [{ status: "submitted" }], applications_used: 1 });
    const next = applySessionEvent(previous, { event: "application_progress", message: "Generating cover letter" }, {});
    expect(next?.applications_submitted).toEqual(previous.applications_submitted);
    expect(next?.applications_used).toBe(1);
  });

  it("replaces cumulative counts rather than counting replayed events twice", () => {
    const previous = session();
    const event = { event: "application_progress", submitted: 2, failed: 1, skipped: 1 };
    const once = applySessionEvent(previous, event, {});
    expect(applySessionEvent(once, event, {})).toEqual(once);
    expect(once?.applications_used).toBe(4);
    expect(previous.applications_submitted).toEqual([]);
  });

  it("keeps an approval settled when a stale review event arrives", () => {
    expect(applySessionEvent(session(), { event: "shortlist_review", status: "awaiting_review" }, { shortlist: true, settling: "awaiting_review" })?.status).toBe("applying");
    expect(applySessionEvent(null, { event: "status", status: "applying" }, {})).toBeNull();
  });
});
