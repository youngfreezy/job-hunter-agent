import { TERMINAL } from "./run";

const PIPELINE = ["intake", "coaching", "awaiting_coach_review", "discovering", "scoring", "awaiting_review", "tailoring", "applying", "verifying", "reporting", "completed"];
type Approvals = { coach?: boolean; shortlist?: boolean; settling?: string | null };

/** Review interrupts are gates, not backwards pipeline progress. */
export function resolveRunStatus(current: string, incoming: string, source: "stream" | "snapshot", approvals: Approvals = {}): string {
  if (TERMINAL.has(current)) return current;
  if (TERMINAL.has(incoming)) return incoming;
  const approved = (status: string) => status === "awaiting_coach_review" ? approvals.coach : status === "awaiting_review" ? approvals.shortlist : undefined;
  const isReview = (status: string) => status === "awaiting_coach_review" || status === "awaiting_review";
  if (isReview(incoming)) {
    if (approvals.settling === incoming) return current;
    // Durable graph state can reveal a new interrupt even after an earlier approval.
    return source === "snapshot" || !approved(incoming) ? incoming : current;
  }
  if (isReview(current) && !approved(current)) return current;
  const before = PIPELINE.indexOf(current);
  const after = PIPELINE.indexOf(incoming);
  return after >= before || after === -1 ? incoming : current;
}

/** A delayed snapshot must never reselect jobs the user has unchecked. */
export function restoreShortlistSelection(current: Set<string>, ids: string[], initialized: boolean): Set<string> {
  return new Set(initialized ? ids.filter((id) => current.has(id)) : ids);
}
