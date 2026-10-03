import { describe, expect, it } from "vitest";

import { liveViewEnds, liveViewFromEvent } from "./liveView";

const browserbaseEvent = {
  event: "browser_live_view",
  url: "https://www.browserbase.com/devtools-fullscreen/inspector.html?wss=connect.browserbase.com/debug/abc",
  provider: "browserbase",
  browserbase_session_id: "sess-123",
  job_id: "job-9",
  timestamp: "2026-10-03T12:00:00.000Z",
};

describe("liveViewFromEvent", () => {
  it("builds panel state from a Browserbase live view event", () => {
    expect(liveViewFromEvent(browserbaseEvent)).toEqual({
      url: browserbaseEvent.url,
      provider: "browserbase",
      browserbaseSessionId: "sess-123",
      jobId: "job-9",
      receivedAt: "2026-10-03T12:00:00.000Z",
    });
  });

  it("reads the payload from evt.data when the event is nested", () => {
    const { event, timestamp, ...data } = browserbaseEvent;
    expect(liveViewFromEvent({ event, timestamp, data })?.jobId).toBe("job-9");
  });

  it("ignores other event types", () => {
    expect(liveViewFromEvent({ ...browserbaseEvent, event: "application_progress" })).toBeNull();
  });

  it("ignores providers that are not embeddable", () => {
    expect(liveViewFromEvent({ ...browserbaseEvent, provider: "cdp" })).toBeNull();
    expect(liveViewFromEvent({ ...browserbaseEvent, provider: undefined })).toBeNull();
  });

  it("refuses non-https urls", () => {
    expect(liveViewFromEvent({ ...browserbaseEvent, url: "javascript:alert(1)" })).toBeNull();
    expect(liveViewFromEvent({ ...browserbaseEvent, url: "http://insecure.example" })).toBeNull();
    expect(liveViewFromEvent({ ...browserbaseEvent, url: "" })).toBeNull();
  });

  it("tolerates a missing session id", () => {
    expect(liveViewFromEvent({ ...browserbaseEvent, browserbase_session_id: null })?.browserbaseSessionId).toBeNull();
  });
});

describe("liveViewEnds", () => {
  it("closes on terminal events only", () => {
    expect(liveViewEnds({ event: "done" })).toBe(true);
    expect(liveViewEnds({ event: "error" })).toBe(true);
    expect(liveViewEnds({ event: "application_submitted" })).toBe(false);
    expect(liveViewEnds({ event: "browser_live_view" })).toBe(false);
  });
});
