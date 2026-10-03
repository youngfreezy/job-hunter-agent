// Copyright (c) 2026 V2 Software LLC. All rights reserved.

/**
 * Shared vocabulary for runs (the backend calls them sessions): names, the five
 * pipeline phases, the two approval gates, status words and the outcome line.
 */

export type PhaseKey = "resume" | "search" | "shortlist" | "apply" | "report";
export type PhaseState = "done" | "current" | "todo" | "empty";
export type GateState = "passed" | "open" | "todo";

export const PHASES: { key: PhaseKey; label: string }[] = [
  { key: "resume", label: "Resume" },
  { key: "search", label: "Search" },
  { key: "shortlist", label: "Shortlist" },
  { key: "apply", label: "Apply" },
  { key: "report", label: "Report" },
];

const STATUS_PHASE: Record<string, PhaseKey> = {
  intake: "resume",
  coaching: "resume",
  awaiting_coach_review: "resume",
  discovering: "search",
  scoring: "shortlist",
  awaiting_review: "shortlist",
  tailoring: "apply",
  applying: "apply",
  needs_intervention: "apply",
  verifying: "report",
  reporting: "report",
  completed: "report",
  failed: "report",
};

const RESUME_NODE_PHASE: Record<string, PhaseKey> = {
  discovery: "search",
  scoring: "shortlist",
  application: "apply",
  tailoring: "apply",
};

/** Sentence-case status words, one map for every screen. */
export const STATUS_LABELS: Record<string, string> = {
  intake: "Starting",
  coaching: "Reviewing your resume",
  awaiting_coach_review: "Resume waiting for you",
  discovering: "Searching job boards",
  scoring: "Ranking matches",
  awaiting_review: "Shortlist waiting for you",
  tailoring: "Tailoring resumes",
  applying: "Applying",
  needs_intervention: "Needs your help",
  verifying: "Checking submissions",
  reporting: "Writing the report",
  paused: "Paused",
  completed: "Finished",
  failed: "Stopped with an error",
};

export const NEEDS_YOU = new Set(["awaiting_coach_review", "awaiting_review", "needs_intervention", "paused"]);
export const TERMINAL = new Set(["completed", "failed"]);

export function isRunning(status: string) {
  return !TERMINAL.has(status) && !NEEDS_YOU.has(status);
}

export function currentPhase(
  status: string,
  pauseNode?: string | null,
  statusBeforePause?: string | null
): PhaseKey {
  if (status === "paused") {
    if (pauseNode && RESUME_NODE_PHASE[pauseNode]) return RESUME_NODE_PHASE[pauseNode];
    if (statusBeforePause && STATUS_PHASE[statusBeforePause]) return STATUS_PHASE[statusBeforePause];
    return "apply";
  }
  return STATUS_PHASE[status] ?? "resume";
}

/** "Applied AI Engineer +5 · San Francisco" */
export function runName(run: { keywords?: string[]; locations?: string[]; remote_only?: boolean }) {
  const kw = run.keywords ?? [];
  const role = kw.length === 0 ? "Search" : kw.length === 1 ? kw[0] : `${kw[0]} +${kw.length - 1}`;
  const place = run.remote_only ? "Remote" : run.locations?.[0];
  return place ? `${role} · ${place}` : role;
}

export interface LedgerPhase {
  key: PhaseKey;
  label: string;
  count: number | null;
  unit: string;
  state: PhaseState;
  reason?: string;
}

export interface LedgerInput {
  status: string;
  pauseNode?: string | null;
  statusBeforePause?: string | null;
  coachScore?: number | null;
  found?: number | null;
  shortlisted?: number | null;
  attempted?: number | null;
  submitted?: number | null;
  failed?: number | null;
  threshold?: number | null;
}

/** Builds the five phases and two gates from whatever counts are known. Unknown counts stay null. */
export function buildLedger(input: LedgerInput): {
  phases: LedgerPhase[];
  gates: { coach: GateState; shortlist: GateState };
} {
  const { status } = input;
  const finished = TERMINAL.has(status);
  let idx = PHASES.findIndex(
    (p) => p.key === currentPhase(status, input.pauseNode, input.statusBeforePause)
  );

  const counts: Record<PhaseKey, { count: number | null; unit: string }> = {
    resume: { count: input.coachScore ?? null, unit: input.coachScore != null ? "of 100" : "" },
    search: { count: input.found ?? null, unit: "postings" },
    shortlist: { count: input.shortlisted ?? null, unit: input.shortlisted === 1 ? "job" : "jobs" },
    apply: { count: input.attempted ?? null, unit: "attempted" },
    report: { count: input.submitted ?? null, unit: "submitted" },
  };

  // A failed run stops at the last phase that reported a count.
  if (status === "failed") {
    let known = 0;
    PHASES.forEach((p, i) => {
      if (counts[p.key].count != null) known = i;
    });
    idx = Math.max(0, known);
  }

  // Once a later phase has started, earlier unknown counts that must be zero
  // (nothing shortlisted means nothing attempted) are filled in.
  if (finished && input.shortlisted === 0) {
    counts.apply.count = counts.apply.count ?? 0;
    counts.report.count = counts.report.count ?? 0;
  }

  const phases: LedgerPhase[] = PHASES.map((p, i) => {
    const c = counts[p.key];
    let state: PhaseState;
    if (i < idx || (finished && i <= idx)) state = "done";
    else if (i === idx) state = "current";
    else state = "todo";
    if ((state === "done" || finished) && c.count === 0 && p.key !== "resume") state = "empty";
    if (finished && i > idx) state = c.count === 0 ? "empty" : "todo";
    return { ...p, count: c.count, unit: c.unit, state };
  });

  // The reason line goes under the first phase whose count drops to zero.
  const firstZero = phases.findIndex((p) => p.key !== "resume" && p.count === 0);
  if (firstZero >= 0) {
    const p = phases[firstZero];
    const before = firstZero > 0 ? phases[firstZero - 1].count : null;
    if (p.key === "search") p.reason = "No postings matched your roles and location";
    else if (p.key === "shortlist")
      p.reason =
        before && input.threshold != null
          ? `0 of ${before} scored ${input.threshold} or higher`
          : before
          ? `0 of ${before} passed your filters`
          : "Nothing passed your filters";
    else if (p.key === "apply") p.reason = "No jobs were approved";
    else if (p.key === "report" && (input.failed ?? 0) > 0)
      p.reason = `${input.failed} ${input.failed === 1 ? "application" : "applications"} failed`;
  }

  const coach: GateState =
    status === "awaiting_coach_review" ? "open" : idx > 0 ? "passed" : "todo";
  const shortlist: GateState =
    status === "awaiting_review"
      ? "open"
      : idx > 2 && input.shortlisted !== 0 && !(finished && input.attempted === 0)
      ? "passed"
      : "todo";

  return {
    phases,
    gates: { coach, shortlist },
  };
}

export type OutcomeTone = "running" | "needs" | "sent" | "neutral" | "failed";

/** One honest line per run. A run that sent nothing never reads as success. */
export function runOutcome(run: { status: string; submitted?: number; failed?: number }): {
  tone: OutcomeTone;
  label: string;
} {
  const sent = run.submitted ?? 0;
  const failed = run.failed ?? 0;
  if (NEEDS_YOU.has(run.status)) return { tone: "needs", label: STATUS_LABELS[run.status] };
  if (run.status === "failed")
    return { tone: "failed", label: sent > 0 ? `Stopped with an error · ${sent} sent` : "Stopped with an error" };
  if (run.status === "completed") {
    if (sent === 0 && failed > 0) return { tone: "failed", label: `Finished · ${failed} failed, nothing sent` };
    if (sent === 0) return { tone: "neutral", label: "Finished · nothing sent" };
    return { tone: "sent", label: failed > 0 ? `Finished · ${sent} sent, ${failed} failed` : `Finished · ${sent} sent` };
  }
  return { tone: "running", label: STATUS_LABELS[run.status] ?? "Running" };
}

/** "+2:41" from seconds since the run started. */
export function formatElapsed(seconds: number) {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = (s % 60).toString().padStart(2, "0");
  return h > 0 ? `+${h}:${m.toString().padStart(2, "0")}:${sec}` : `+${m}:${sec}`;
}

/** "3 min", "1 h 12 min" */
export function formatDuration(minutes: number) {
  const m = Math.max(0, Math.round(minutes));
  if (m < 1) return "under a minute";
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

/** "Today 8:40", "Sep 30 14:05" */
export function formatStarted(value?: string | null) {
  if (!value) return "";
  const d = new Date(value);
  if (isNaN(d.getTime())) return "";
  const time = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return `Today ${time}`;
  const y = new Date(today);
  y.setDate(today.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return `Yesterday ${time}`;
  return `${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })} ${time}`;
}

/** Score cutoff the backend applies: 30 + strictness × 40 (scoring.py). */
export function scoreThreshold(config?: { scoring_strictness?: unknown; discovery_mode?: unknown } | null) {
  if (!config) return 50;
  if (config.discovery_mode === "manual_urls") return null;
  const s = typeof config.scoring_strictness === "number" ? config.scoring_strictness : 0.5;
  return Math.round(30 + s * 40);
}
