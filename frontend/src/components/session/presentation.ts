// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { applicationOutcomeCounts } from "../../lib/application-outcomes";

import {
  buildLedger,
  currentPhase,
  formatDuration,
  formatElapsed,
  isRunning,
  NEEDS_YOU,
  pipelineEventText,
  runOutcome,
  scoreThreshold,
  STATUS_LABELS,
  TERMINAL,
  type OutcomeTone,
  type PhaseKey
} from "../../lib/run";

import { compressEvents } from "./event-log";
import type { ScoredJobData, SessionData, SessionSummaryData, SSEEvent } from "./types";
const AGENT_PHASE: Record<string, PhaseKey> = {
  intake: "resume",
  career_coach: "resume",
  coaching: "resume",
  coach: "resume",
  discovery: "search",
  scoring: "shortlist",
  backfill: "shortlist",
  resume_tailor: "apply",
  tailoring: "apply",
  application: "apply",
  browser_live_view: "apply",
  verification: "report",
  reporting: "report",
};

const AGENT_DISPLAY_NAMES: Record<string, string> = {
  intake: "Setup",
  coach: "Coach",
  career_coach: "Coach",
  coaching: "Coach",
  discovery: "Search",
  scoring: "Ranking",
  resume_tailor: "Tailor",
  tailoring: "Tailor",
  application: "Apply",
  browser_live_view: "Browser",
  verification: "Verify",
  reporting: "Summary",
  backfill: "Backfill",
  status: "Status",
  system: "System",
};

export function sessionPresentation(session: SessionData, sessionSummary: SessionSummaryData | null, events: SSEEvent[], shortlistJobs: ScoredJobData[], elapsedSeconds: number, needsAttention: boolean) {
  const elapsedMin = Math.floor(elapsedSeconds / 60);
  const elapsedSec = elapsedSeconds % 60;
  const surfacedEvents = compressEvents(events);
  const discoveredFromEvents = [...events].reverse().find((event) => typeof event.jobs_found === "number")?.jobs_found ?? null;
  const status = session.status;
  const finished = TERMINAL.has(status);
  const running = isRunning(status);
  const submittedCount = sessionSummary?.total_applied ?? session.applications_submitted?.length ?? 0;
  const { failed: failedCount, uncertain: uncertainCount } = applicationOutcomeCounts(session.applications_failed, sessionSummary);
  const skippedCount = sessionSummary?.total_skipped ?? (Array.isArray(session.applications_skipped) ? session.applications_skipped.length : session.applications_skipped ?? 0);
  const questionCount = Object.keys(session.application_questions ?? {}).length;
  const queuedEmployerCount = Object.values(session.employer_application_queue ?? {}).filter((job) => job.status === "queued").length;
  const discovered = (session as unknown as { discovered_jobs?: unknown[] }).discovered_jobs;
  const found =
    sessionSummary?.total_discovered ??
    (Array.isArray(discovered) && discovered.length > 0 ? discovered.length : null) ??
    discoveredFromEvents;
  const phaseKey = currentPhase(status, session.pause_resume_node, session.status_before_pause);
  const pastShortlist = ["apply", "report"].includes(phaseKey) || status === "awaiting_review";
  const scoredCount = sessionSummary
    ? sessionSummary.total_scored
    : pastShortlist
      ? session.scored_jobs?.length ?? shortlistJobs.length
      : null;
  const threshold = scoreThreshold(session.session_config as { scoring_strictness?: unknown; discovery_mode?: unknown });
  const approvalRecorded = Boolean(session.application_queue?.length)
    || events.some((event) => ["application_start", "application_progress", "application_submitted", "application_failed"].includes(event.event));
  const recordedAttempts = submittedCount + failedCount + uncertainCount + skippedCount;
  // An interrupted approved job can have browser activity without a durable result.
  const attempted = finished
    ? approvalRecorded && recordedAttempts === 0 ? null : recordedAttempts
    : session.applications_used || null;
  const ledger = buildLedger({
    status,
    pauseNode: session.pause_resume_node,
    statusBeforePause: session.status_before_pause,
    coachScore: session.coach_output?.resume_score?.overall ?? null,
    found,
    shortlisted: scoredCount,
    selectedJobUrls: session.session_config?.discovery_mode === "manual_urls"
      ? session.session_config.job_urls ?? session.job_urls ?? []
      : undefined,
    attempted,
    shortlistApproved: approvalRecorded,
    submitted: finished || phaseKey === "apply" || phaseKey === "report" ? submittedCount : null,
    failed: failedCount,
    uncertain: uncertainCount,
    threshold,
  });
  const shortlisted = ledger.phases.find((phase) => phase.key === "shortlist")?.count ?? null;

  const durationMin =
    sessionSummary?.duration_minutes ??
    (() => {
      const last = [...events].reverse().find((e) => e.timestamp)?.timestamp;
      if(!last || !session.created_at) return null;
      return (new Date(last).getTime() - new Date(session.created_at).getTime()) / 60000;
    })();

  const finishedReason = (() => {
    if(uncertainCount > 0) return "Confirmation pending—check before retrying";
    if(submittedCount > 0)
      return failedCount > 0 ? `${submittedCount} sent, ${failedCount} failed` : `${submittedCount} sent`;
    if(found === 0) return "no postings matched your roles and location";
    if(shortlisted === 0) return session.session_config?.discovery_mode === "manual_urls" ? "no job links were selected" : "no jobs met your score threshold";
    if(questionCount > 0) return `${questionCount} ${questionCount === 1 ? "application needs" : "applications need"} your answers · nothing sent`;
    if(queuedEmployerCount > 0) return `${queuedEmployerCount} employer ${queuedEmployerCount === 1 ? "application" : "applications"} queued · nothing sent`;
    if(skippedCount > 0) return `${skippedCount} skipped${failedCount > 0 ? `, ${failedCount} failed` : ""} · nothing sent`;
    if(failedCount > 0) return "every application failed";
    return approvalRecorded ? "approved jobs have no recorded application result" : "no application results recorded";
  })();

  const elapsedLabel = `${elapsedMin}:${elapsedSec.toString().padStart(2, "0")}`;
  const stateLine =
    status === "completed"
      ? `Finished${durationMin != null ? ` in ${formatDuration(durationMin)}` : ""} · ${finishedReason}`
      : status === "failed"
        ? uncertainCount > 0 ? "Stopped · Confirmation pending—check before retrying" : `Stopped${submittedCount > 0 ? ` · ${submittedCount} sent before it stopped` : approvalRecorded && recordedAttempts === 0 ? " · no submission confirmed" : " · nothing was sent"}`
        : status === "awaiting_coach_review"
          ? "Waiting for you to approve your resume"
          : status === "awaiting_review"
            ? `Waiting for your approval · ${shortlistJobs.length || session.scored_jobs?.length || 0} jobs on the shortlist`
            : status === "paused"
              ? "Paused · resume when you're ready"
              : `${STATUS_LABELS[status] ?? "Running"} · running ${elapsedLabel}`;

  const stateTone: OutcomeTone = finished
    ? runOutcome({ status, submitted: submittedCount, failed: failedCount, uncertain: uncertainCount }).tone
    : NEEDS_YOU.has(status) || needsAttention
      ? "needs"
      : "running";

  // Event log: deduplicated, grouped by phase, with time since the run started.
  const startMs = session.created_at ? new Date(session.created_at).getTime() : null;
  const logRows = (() => {
    const seen = new Set<string>();
    const rows: { group: PhaseKey; t: string; step: string; text: string; tone: "default" | "error" | "needs" }[] = [];
    let group: PhaseKey = "resume";
    for(const evt of surfacedEvents) {
      const agent = (evt.event?.endsWith("_progress") ? evt.event.replace("_progress", "") : evt.agent || evt.event || "system") as string;
      const text = pipelineEventText(evt);
      if(!text) continue;
      const key = `${agent}|${text}|${evt.timestamp ?? ""}`;
      if(seen.has(key)) continue;
      seen.add(key);
      group = AGENT_PHASE[agent] ?? group;
      const ts = evt.timestamp ? new Date(evt.timestamp).getTime() : NaN;
      rows.push({
        group,
        t: startMs && !isNaN(ts) ? formatElapsed((ts - startMs) / 1000) : "",
        step: AGENT_DISPLAY_NAMES[agent] ?? "Agent",
        text,
        tone:
          evt.event === "error" || evt.error
            ? "error"
            : ["coach_review", "shortlist_review", "needs_intervention", "login_required"].includes(evt.event)
              ? "needs"
              : "default",
      });
    }
    return rows;
  })();

  return { status, finished, running, submittedCount, failedCount, uncertainCount, skippedCount, questionCount, queuedEmployerCount, found, threshold, ledger, shortlisted, durationMin, stateLine, stateTone, logRows };
}
export type SessionPresentation = ReturnType<typeof sessionPresentation>;
