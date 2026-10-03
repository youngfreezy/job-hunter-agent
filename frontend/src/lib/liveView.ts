// Copyright (c) 2026 V2 Software LLC. All rights reserved.

/**
 * Live browser view state derived from `browser_live_view` SSE events.
 *
 * In Browserbase mode the backend emits one of these when it opens a cloud
 * browser for a job. The Live View URL is embeddable, so the session page
 * renders it in an iframe instead of a screenshot feed for that job.
 */

export interface LiveViewState {
  url: string;
  provider: string;
  browserbaseSessionId: string | null;
  jobId: string;
  receivedAt: string;
}

export interface LiveViewEventLike {
  event?: string;
  url?: unknown;
  provider?: unknown;
  browserbase_session_id?: unknown;
  job_id?: unknown;
  timestamp?: string;
  data?: Record<string, unknown>;
}

const EMBEDDABLE_PROVIDERS = new Set(["browserbase"]);

function isHttpsUrl(value: unknown): value is string {
  if (typeof value !== "string" || !value) return false;
  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
}

/**
 * Build the panel state from an SSE event, or null when the event is not an
 * embeddable live view (wrong event type, non-Browserbase provider, or a URL
 * that is not https — the page must never iframe an arbitrary scheme).
 */
export function liveViewFromEvent(evt: LiveViewEventLike): LiveViewState | null {
  if (evt.event !== "browser_live_view") return null;
  const payload = (evt.data && typeof evt.data === "object" ? evt.data : evt) as LiveViewEventLike;
  const provider = typeof payload.provider === "string" ? payload.provider : "";
  if (!EMBEDDABLE_PROVIDERS.has(provider)) return null;
  if (!isHttpsUrl(payload.url)) return null;
  return {
    url: payload.url,
    provider,
    browserbaseSessionId:
      typeof payload.browserbase_session_id === "string" && payload.browserbase_session_id
        ? payload.browserbase_session_id
        : null,
    jobId: typeof payload.job_id === "string" ? payload.job_id : String(payload.job_id ?? ""),
    receivedAt: evt.timestamp || new Date().toISOString(),
  };
}

/** Events after which the cloud browser is gone and the panel should close. */
export function liveViewEnds(evt: { event?: string }): boolean {
  return evt.event === "done" || evt.event === "error";
}
