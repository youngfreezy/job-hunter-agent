// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { API_BASE } from "./config";
import { getAuthHeaders } from "./auth";
import { AuthenticatedEventSource } from "../event-stream";
import type { SSEEventType } from "./types";

export type SSEConnection = AuthenticatedEventSource;

export function createAuthenticatedStream(url: string): SSEConnection {
  return new AuthenticatedEventSource(url, getAuthHeaders);
}

export async function createSSEConnection(sessionId: string): Promise<SSEConnection> {
  return createAuthenticatedStream(`${API_BASE}/api/sessions/${sessionId}/stream`);
}

const SESSION_EVENT_TYPES: SSEEventType[] = [
  "status",
  "coaching",
  "coach_review",
  "coaching_progress",
  "discovery",
  "discovery_progress",
  "scoring",
  "scoring_progress",
  "tailoring",
  "tailoring_progress",
  "shortlist_review",
  "agent_complete",
  "hitl",
  "application_progress",
  "application_submitted",
  "application_failed",
  "application_start",
  "application_browser_action",
  "verification_progress",
  "backfill_progress",
  "reporting_progress",
  "needs_intervention",
  "ready_to_submit",
  "login_required",
  "login_complete",
  "captcha_detected",
  "browser_live_view",
  "browser_live_view_ended",
  "done",
  "error",
];

/** Route the same session protocol for signed-in and trial subscribers. */
export function subscribeToSessionEvents(
  source: SSEConnection,
  onEvent: (event: Record<string, unknown>) => void,
  onConnectionChange?: (connected: boolean) => void
): () => void {
  let cancelled = false;
  source.onopen = () => { if (!cancelled) onConnectionChange?.(true); };
  source.onerror = () => {
    if (!cancelled && source.readyState !== AuthenticatedEventSource.OPEN) {
      onConnectionChange?.(false);
    }
  };
  const receive = (message: MessageEvent, eventType?: SSEEventType) => {
    if (cancelled) return;
    try {
      const data = JSON.parse(message.data);
      onEvent({
        ...data,
        event: eventType || data.event || "message",
        timestamp: data.timestamp || new Date().toISOString(),
      });
      if (eventType === "done") source.close();
    } catch {
      // Ignore malformed events without losing the remaining stream.
    }
  };
  for (const eventType of SESSION_EVENT_TYPES) {
    source.addEventListener(eventType, (event: MessageEvent) => receive(event, eventType));
  }
  source.onmessage = (event: MessageEvent) => receive(event);
  return () => { cancelled = true; source.close(); };
}

export function connectSSE(
  sessionId: string,
  onEvent: (event: Record<string, unknown>) => void,
  onConnectionChange?: (connected: boolean) => void
): () => void {
  let cancelled = false;
  let unsubscribe: (() => void) | undefined;
  void createSSEConnection(sessionId).then(source => {
    if (cancelled) source.close();
    else unsubscribe = subscribeToSessionEvents(source, onEvent, onConnectionChange);
  });
  return () => { cancelled = true; unsubscribe?.(); };
}
