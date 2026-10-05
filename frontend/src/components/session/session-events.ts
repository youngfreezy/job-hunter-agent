import { resolveRunStatus } from "../../lib/run-status";
import type { SessionData, SSEEvent } from "./types";

export function applySessionEvent(prev: SessionData | null, evt: SSEEvent, approvals: Parameters<typeof resolveRunStatus>[3]): SessionData | null {
  if(!prev) return prev;
  const updates: Partial<SessionData> = {};
  if(
    evt.status &&
    (evt.event === "status" ||
      evt.event === "done" ||
      evt.event === "coach_review" ||
      evt.event === "shortlist_review")
  ) {
    updates.status = resolveRunStatus(prev.status, evt.status, "stream", approvals);
  }
  if(evt.coach_output)
    updates.coach_output = evt.coach_output as unknown as SessionData["coach_output"];
  if(Array.isArray(evt.keywords) && evt.keywords.length > 0) updates.keywords = evt.keywords;
  // Track application counts from progress events (only when
  // the event actually carries count fields — step-level events
  // like "Generating cover letter..." don't have them and would
  // reset counts to 0).
  if(
    evt.event === "application_progress" &&
    (typeof evt.submitted === "number" ||
      typeof evt.failed === "number" ||
      typeof evt.skipped === "number")
  ) {
    const sub = typeof evt.submitted === "number" ? evt.submitted : 0;
    const fail = typeof evt.failed === "number" ? evt.failed : 0;
    const skip = typeof evt.skipped === "number" ? evt.skipped : 0;
    updates.applications_used = sub + fail + skip;
    updates.applications_submitted = Array(sub).fill({
      job_id: "",
      status: "submitted",
    });
    updates.applications_failed = Array(fail).fill({
      job_id: "",
      error_message: "",
    });
    updates.applications_skipped = skip;
  }
  if(evt.employer_application_queue) updates.employer_application_queue = evt.employer_application_queue;
  if(evt.application_questions) updates.application_questions = evt.application_questions;
  return { ...prev, ...updates };
}
