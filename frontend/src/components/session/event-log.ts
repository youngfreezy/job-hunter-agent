// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import {
  STATUS_LABELS
} from "../../lib/run";

import type { SSEEvent } from "./types";
export function compressEvents(events: SSEEvent[]): SSEEvent[] {
  const compressed: SSEEvent[] = [];

  for(const event of events) {
    const summary = String(event.step || event.message || event.status || event.event || "");
    const signature = [event.event, event.agent || "", summary.trim()].join("|");
    const previous = compressed[compressed.length - 1];
    const previousSummary = previous
      ? String(previous.step || previous.message || previous.status || previous.event || "")
      : "";
    const previousSignature = previous
      ? [previous.event, previous.agent || "", previousSummary.trim()].join("|")
      : "";

    if(previous && signature === previousSignature) {
      compressed[compressed.length - 1] = event;
      continue;
    }

    if(
      event.event === "status" &&
      previous &&
      previous.event === "status" &&
      previous.status === event.status
    ) {
      compressed[compressed.length - 1] = event;
      continue;
    }

    compressed.push(event);
  }

  return compressed.slice(-50);
}

export function checkpointLabel(status: string): string {
  switch(status) {
    case "awaiting_coach_review":
      return "Resume approval";
    case "awaiting_review":
      return "Shortlist approval";
    case "paused":
      return "Paused run";
    default:
      return STATUS_LABELS[status] || status;
  }
}
