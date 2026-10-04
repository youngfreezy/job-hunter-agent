// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { applicationOutcomeCounts } from "@/lib/application-outcomes";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ChatPanel, type ChatMessage } from "@/components/ChatPanel";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { CoachPanel } from "@/components/CoachPanel";
import { LiveBrowserPanel } from "@/components/LiveBrowserPanel";
import { ApplicationFollowups, type ApplicationQuestion, type EmployerApplication } from "@/components/ApplicationFollowups";
import { addApplicationAnswer, type AnswerScope } from "@/lib/applicationAnswers";
import { resolveRunStatus, restoreShortlistSelection } from "@/lib/run-status";
import { liveViewEnds, liveViewFromEvent, type LiveViewState } from "@/lib/liveView";
import { PipelineLedger } from "@/components/run/PipelineLedger";
import { AdjustDialog, type RunOverrides } from "@/components/run/AdjustDialog";
import { StatusDot } from "@/components/ui/status-dot";
import { cn } from "@/lib/utils";
import {
  NEEDS_YOU,
  PHASES,
  STATUS_LABELS,
  TERMINAL,
  buildLedger,
  currentPhase,
  formatDuration,
  formatElapsed,
  isRunning,
  runOutcome,
  scoreThreshold,
  shouldRefreshSession,
  pipelineEventText,
  type OutcomeTone,
  type PhaseKey,
} from "@/lib/run";
import {
  getSession,
  getApplicationRules,
  updateApplicationRules,
  connectSSE,
  sendSteer,
  sendCoachChat,
  submitReview,
  submitCoachReview,
  resumeIntervention,
  submitDecision,
  listCheckpoints,
  rewindSession,
  confirmLogin,
  killSession,
  rerunSession,
  resumeSession,
} from "@/lib/api";
import type { Checkpoint } from "@/lib/api";
import type { CoachOutput } from "@/lib/api";

type SessionData = {
  employer_application_queue?: Record<string, EmployerApplication>;
  application_questions?: Record<string, ApplicationQuestion>;
  session_summary?: boolean;
  session_id: string;
  status: string;
  pause_resume_node?: string | null;
  status_before_pause?: string | null;
  keywords: string[];
  locations?: string[];
  remote_only?: boolean;
  salary_min?: number | null;
  scored_jobs: Array<{
    job: {
      id: string;
      title: string;
      company: string;
      location: string;
      url: string;
      board: string;
    };
    score: number;
    breakdown: Record<string, number>;
  }>;
  applications_submitted: Array<{
    job_id?: string;
    job?: { id: string; title: string; company: string; url: string; board: string };
    status: string;
    submitted_at?: string;
  }>;
  applications_failed: Array<{
    job_id?: string;
    job?: { id: string; title: string; company: string; url: string; board: string };
    error_category?: string;
    error_message?: string;
    error?: string;
  }>;
  coach_output?: CoachOutput;
  coach_chat_history?: Array<{ role: string; text: string }>;
  linkedin_url?: string;
  applications_used: number;
  applications_skipped: string[] | number;
  created_at?: string;
  session_config?: {
    discovery_mode?: string;
    job_urls?: string[];
    [key: string]: unknown;
  };
  job_urls?: string[];
};

type SessionSummaryData = {
  session_id: string;
  total_discovered: number;
  total_scored: number;
  total_applied: number;
  total_failed: number;
  total_uncertain?: number;
  total_skipped: number;
  top_companies: string[];
  avg_fit_score: number;
  resume_score: { overall: number } | null;
  duration_minutes: number;
  next_steps: string[];
};

type ScoredJobData = {
  job: {
    id: string;
    title: string;
    company: string;
    location: string;
    url: string;
    board: string;
  };
  score: number;
  score_breakdown?: Record<string, number>;
  reasons?: string[];
  fit_summary?: string;
};

type SSEEvent = {
  employer_application_queue?: Record<string, EmployerApplication>;
  application_questions?: Record<string, ApplicationQuestion>;
  event: string;
  agent?: string;
  status?: string;
  message?: string;
  data?: Record<string, unknown>;
  timestamp?: string;
  jobs_found?: number;
  scored_count?: number;
  coach_output?: Record<string, unknown>;
  scored_jobs?: ScoredJobData[];
  agent_statuses?: Record<string, string>;
  keywords?: string[];
  locations?: string[];
  session_summary?: SessionSummaryData;
  step?: string;
  progress?: number;
  board?: string;
  count?: number;
  error?: boolean;
  submitted?: number;
  failed?: number;
  skipped?: number;
  current?: number;
  total?: number;
  section?: string;
  success?: boolean;
  results?: Array<{
    section: string;
    label: string;
    success: boolean;
    error?: string | null;
  }>;
};

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

function compressEvents(events: SSEEvent[]): SSEEvent[] {
  const compressed: SSEEvent[] = [];

  for (const event of events) {
    const summary = String(event.step || event.message || event.status || event.event || "");
    const signature = [event.event, event.agent || "", summary.trim()].join("|");
    const previous = compressed[compressed.length - 1];
    const previousSummary = previous
      ? String(previous.step || previous.message || previous.status || previous.event || "")
      : "";
    const previousSignature = previous
      ? [previous.event, previous.agent || "", previousSummary.trim()].join("|")
      : "";

    if (previous && signature === previousSignature) {
      compressed[compressed.length - 1] = event;
      continue;
    }

    if (
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

function checkpointLabel(status: string): string {
  switch (status) {
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

function QuickApplyUrls({
  urls,
  submitted,
  failed,
}: {
  urls: string[];
  submitted: number;
  failed: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const processed = submitted + failed;
  const total = urls.length;

  function hostLabel(url: string) {
    try {
      const h = new URL(url).hostname.replace("www.", "");
      // Show a short recognizable label
      if (h.includes("greenhouse")) return "Greenhouse";
      if (h.includes("lever")) return "Lever";
      if (h.includes("ashby")) return "Ashby";
      if (h.includes("workday")) return "Workday";
      if (h.includes("linkedin")) return "LinkedIn";
      if (h.includes("deloitte")) return "Deloitte";
      if (h.includes("aplitrak")) return "Aplitrak";
      return h.split(".")[0];
    } catch {
      return url.slice(0, 30);
    }
  }

  return (
    <div className="border-t border-border/30 pt-2">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center justify-between text-xs"
      >
        <span className="uppercase tracking-wider text-muted-foreground">
          Quick Apply
        </span>
        <span className="flex items-center gap-1.5 font-medium">
          <span className="text-blue-600 dark:text-blue-400">
            {processed}/{total}
          </span>
          <svg
            className={`h-3 w-3 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </span>
      </button>

      {/* Progress bar */}
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700">
        <div
          className="h-full rounded-full bg-primary transition-all duration-500"
          style={{ width: `${total > 0 ? (processed / total) * 100 : 0}%` }}
        />
      </div>

      {expanded && (
        <ul className="mt-2 space-y-1">
          {urls.map((url, i) => (
            <li key={i} className="flex items-center gap-1.5 text-xs">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-300 dark:bg-zinc-600" />
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="truncate text-blue-600 hover:underline dark:text-blue-400"
                title={url}
              >
                {hostLabel(url)}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function SessionPage() {
  const params = useParams();
  const sessionId = params.id as string;
  // Send Gmail token to backend via server-side proxy (tokens never touch the browser)
  const gmailTokenSent = useRef(false);
  useEffect(() => {
    if (gmailTokenSent.current) return;
    gmailTokenSent.current = true;
    fetch("/api/auth/gmail-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    }).catch(() => {
      // Non-critical — verification codes will fall back to manual entry
      gmailTokenSent.current = false;
    });
  }, [sessionId]);

  const eventsStorageKey = `jh_sse_events_${sessionId}`;
  const sessionStorageKey = `jh_session_${sessionId}`;

  const [session, setSession] = useState<SessionData | null>(null);
  const [savedAnswerRules, setSavedAnswerRules] = useState("");
  const answerSaveQueue = useRef<Promise<unknown>>(Promise.resolve());
  useEffect(() => {
    let active = true;
    getApplicationRules().then((rules) => { if (active) setSavedAnswerRules(rules); }).catch(() => {});
    return () => { active = false; };
  }, []);
  async function saveAnswer(question: AnswerScope, answer: string) {
    // Serialize cards' saves and reload current rules so separate answers never
    // overwrite one another from a stale page snapshot.
    const operation = answerSaveQueue.current.catch(() => {}).then(async () => {
      const current = await getApplicationRules();
      const result = await updateApplicationRules(addApplicationAnswer(current, question, answer));
      setSavedAnswerRules(result.application_rules);
    });
    answerSaveQueue.current = operation;
    await operation;
  }
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [cacheLoaded, setCacheLoaded] = useState(false);
  useEffect(() => {
    try {
      const cachedEvents = sessionStorage.getItem(eventsStorageKey);
      if (cachedEvents) setEvents(JSON.parse(cachedEvents) as SSEEvent[]);
    } catch { /* stale cache is non-critical */ }
    setCacheLoaded(true);
  }, [eventsStorageKey]);
  const [coachReviewOpen, setCoachReviewOpen] = useState(false);
  const [coachReviewData, setCoachReviewData] = useState<CoachOutput | null>(null);
  const [coachReviewSubmitting, setCoachReviewSubmitting] = useState(false);
  const [shortlistReviewOpen, setShortlistReviewOpen] = useState(false);
  const [shortlistJobs, setShortlistJobs] = useState<ScoredJobData[]>([]);
  const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());
  const [shortlistSubmitting, setShortlistSubmitting] = useState(false);

  // Derived: count selected jobs per company for duplicate warning
  const selectedCompanyCounts = useMemo(() => {
    const counts = new Map<string, number>();
    shortlistJobs.forEach((sj) => {
      if (selectedJobIds.has(sj.job.id)) {
        const key = sj.job.company.toLowerCase().trim();
        counts.set(key, (counts.get(key) || 0) + 1);
      }
    });
    return counts;
  }, [shortlistJobs, selectedJobIds]);

  const [sessionSummary, setSessionSummary] = useState<SessionSummaryData | null>(null);
  const [interventionData, setInterventionData] = useState<{
    job_id: string;
    job_title: string;
    company: string;
    reason: string;
    screenshot?: string;
  } | null>(null);
  const [submitConfirmData, setSubmitConfirmData] = useState<{
    job_id: string;
    job_title: string;
    company: string;
    url: string;
    fields_filled: number;
    screenshot?: string;
  } | null>(null);

  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [rewindLoading, setRewindLoading] = useState(false);
  const [sseKey, setSseKey] = useState(0);
  // Browserbase mode: the cloud browser's Live View for the job being applied to.
  const [liveView, setLiveView] = useState<LiveViewState | null>(null);
  const [sseConnected, setSseConnected] = useState(true);
  const [sseFailCount, setSseFailCount] = useState(0);
  const [loginPrompt, setLoginPrompt] = useState<{
    board: string;
    message: string;
  } | null>(null);
  const [loginConfirming, setLoginConfirming] = useState(false);
  const latestStatusRef = useRef("intake");
  const coachApprovedRef = useRef(false);
  const shortlistApprovedRef = useRef(false);
  const approvalVersionRef = useRef(0);
  const settlingReviewRef = useRef<string | null>(null);
  const shortlistSelectionInitializedRef = useRef(false);
  function restoreShortlist(jobs: ScoredJobData[]) {
    setShortlistJobs(jobs);
    const initialized = shortlistSelectionInitializedRef.current;
    shortlistSelectionInitializedRef.current = true;
    setSelectedJobIds((current) => restoreShortlistSelection(current, jobs.map((sj) => sj.job.id), initialized));
  }

  // Persist events & session to sessionStorage so navigation doesn't lose progress
  useEffect(() => {
    try {
      if (cacheLoaded) sessionStorage.setItem(eventsStorageKey, JSON.stringify(events));
    } catch {
      /* quota exceeded – non-critical */
    }
  }, [events, eventsStorageKey, cacheLoaded]);

  useEffect(() => {
    if (!session) return;
    try {
      sessionStorage.setItem(sessionStorageKey, JSON.stringify(session));
    } catch {
      /* quota exceeded – non-critical */
    }
  }, [session, sessionStorageKey]);

  // Elapsed timer — driven by the session's created_at timestamp from the DB
  const sessionStartTime = session?.created_at ? new Date(session.created_at).getTime() : null;
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  useEffect(() => {
    if (!sessionStartTime) return;
    if (session?.status === "completed" || session?.status === "failed") return;
    setElapsedSeconds(Math.floor((Date.now() - sessionStartTime) / 1000));
    const interval = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - sessionStartTime) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [sessionStartTime, session?.status]);
  const elapsedMin = Math.floor(elapsedSeconds / 60);
  const elapsedSec = elapsedSeconds % 60;
  useEffect(() => {
    const requestedAtApproval = approvalVersionRef.current;
    getSession(sessionId)
      .then((data) => {
        if (requestedAtApproval !== approvalVersionRef.current) return;
        const snapshot = data as unknown as SessionData;
        const s = { ...snapshot, status: resolveRunStatus(latestStatusRef.current, snapshot.status, "snapshot", {
          coach: coachApprovedRef.current, shortlist: shortlistApprovedRef.current, settling: settlingReviewRef.current,
        }) };
        setSession((prev) => prev && TERMINAL.has(prev.status) ? { ...s, status: prev.status } : s);
        latestStatusRef.current = s.status;
        const pastCoach = [
          "discovering",
          "scoring",
          "tailoring",
          "awaiting_review",
          "applying",
          "verifying",
          "reporting",
          "completed",
          "failed",
        ];
        const pastShortlist = ["applying", "verifying", "reporting", "completed", "failed"];
        if (pastCoach.includes(s.status)) coachApprovedRef.current = true;
        if (pastShortlist.includes(s.status)) shortlistApprovedRef.current = true;

        // Restore modals from persisted state on page reload
        if (s.status === "awaiting_coach_review" && s.coach_output) {
          setCoachReviewData(s.coach_output as unknown as CoachOutput);
          setCoachReviewOpen(true);
          if (Array.isArray(s.coach_chat_history) && s.coach_chat_history.length > 0) {
            setChatMessages(
              s.coach_chat_history.map((entry) => ({
                role: entry.role === "assistant" ? "agent" : (entry.role as ChatMessage["role"]),
                text: entry.text,
              }))
            );
          }
        }
        if (s.status === "awaiting_review" && s.scored_jobs && s.scored_jobs.length > 0) {
          const jobs = s.scored_jobs as ScoredJobData[];
          restoreShortlist(jobs);
          setShortlistReviewOpen(true);
        }
        if (s.status === "completed" && s.session_summary) {
          setSessionSummary(s.session_summary as unknown as SessionSummaryData);
        }
      })
      .catch(() => {
        if (requestedAtApproval !== approvalVersionRef.current) return;
        setSession((prev) => prev || {
          session_id: sessionId,
          status: "intake",
          keywords: [],
          scored_jobs: [],
          applications_submitted: [],
          applications_failed: [],
          applications_used: 0,
          applications_skipped: 0,
        });
      });
  }, [sessionId]);

  useEffect(() => {
    const cleanup = connectSSE(sessionId, (event) => {
      const evt = event as unknown as SSEEvent;
      if (evt.event === "ping") return;

      // Browserbase live view: embed the cloud browser instead of a screenshot feed.
      const nextLiveView = liveViewFromEvent(evt);
      if (nextLiveView) setLiveView(nextLiveView);
      if (liveViewEnds(evt)) setLiveView(null);

      setEvents((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.event === evt.event) {
          const lastKey = last.message || last.step || last.status || "";
          const evtKey = evt.message || evt.step || evt.status || "";
          if (lastKey && lastKey === evtKey) return prev;
        }
        return [...prev, evt];
      });


      if (
        evt.status &&
        (evt.event === "status" ||
          evt.event === "done" ||
          evt.event === "coach_review" ||
          evt.event === "shortlist_review")
      ) {
        latestStatusRef.current = resolveRunStatus(latestStatusRef.current, evt.status, "stream", { coach: coachApprovedRef.current, shortlist: shortlistApprovedRef.current, settling: settlingReviewRef.current });
      }

      setSession((prev) => {
        if (!prev) return prev;
        const updates: Partial<SessionData> = {};
        if (
          evt.status &&
          (evt.event === "status" ||
            evt.event === "done" ||
            evt.event === "coach_review" ||
            evt.event === "shortlist_review")
        ) {
          updates.status = resolveRunStatus(prev.status, evt.status, "stream", {
            coach: coachApprovedRef.current, shortlist: shortlistApprovedRef.current, settling: settlingReviewRef.current,
          });
        }
        if (evt.coach_output)
          updates.coach_output = evt.coach_output as unknown as SessionData["coach_output"];
        if (Array.isArray(evt.keywords) && evt.keywords.length > 0) updates.keywords = evt.keywords;
        // Show browser notification for verification code requests
        if (evt.event === "verification_required") {
          if (typeof window !== "undefined" && "Notification" in window) {
            Notification.requestPermission().then((perm) => {
              if (perm === "granted") {
                new Notification("Verification Code Required", {
                  body:
                    (evt.message as string) ||
                    "Check your email for a verification code and enter it in the browser window.",
                  icon: "/favicon.ico",
                });
              }
            });
          }
        }
        // Track application counts from progress events (only when
        // the event actually carries count fields — step-level events
        // like "Generating cover letter..." don't have them and would
        // reset counts to 0).
        if (
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
        if (evt.employer_application_queue) updates.employer_application_queue = evt.employer_application_queue;
        if (evt.application_questions) updates.application_questions = evt.application_questions;
        return { ...prev, ...updates };
      });

      // Sparse result events do not contain cumulative counts. Replace totals
      // from durable state, so repeated/replayed events cannot double-count.
      // Routine progress events already carry totals and need no extra request.
      if (
        shouldRefreshSession(evt)
      ) {
        const requestedAtApproval = approvalVersionRef.current;
        getSession(sessionId)
          .then((data) => {
            if (requestedAtApproval !== approvalVersionRef.current) return;
            const s = data as unknown as SessionData;
            const nextStatus = resolveRunStatus(latestStatusRef.current, s.status, "snapshot", {
              coach: coachApprovedRef.current, shortlist: shortlistApprovedRef.current, settling: settlingReviewRef.current,
            });
            latestStatusRef.current = nextStatus;
            // Once durable state has advanced, a later interrupt can be a new gate.
            if (s.status === nextStatus && s.status !== "awaiting_coach_review" && s.status !== "awaiting_review") settlingReviewRef.current = null;
            if (nextStatus === "awaiting_coach_review") {
              coachApprovedRef.current = false;
              if (s.coach_output) {
                setCoachReviewData(s.coach_output as unknown as CoachOutput);
                setCoachReviewOpen(true);
              }
            }
            if (nextStatus === "awaiting_review") {
              shortlistApprovedRef.current = false;
              if (s.scored_jobs?.length) {
                const jobs = s.scored_jobs as ScoredJobData[];
                restoreShortlist(jobs);
                setShortlistReviewOpen(true);
              }
            }
            setSession((prev) => ({ ...s, status: prev ? resolveRunStatus(prev.status, nextStatus, "snapshot", {
              coach: coachApprovedRef.current, shortlist: shortlistApprovedRef.current, settling: settlingReviewRef.current,
            }) : nextStatus }));
          })
          .catch(() => {});
      }

      if (evt.event === "coach_review" && evt.coach_output) {
        setCoachReviewData(evt.coach_output as unknown as CoachOutput);
        const history = (evt.data?.coach_chat_history ||
          (
            evt as unknown as {
              coach_chat_history?: Array<{ role: string; text: string }>;
            }
          ).coach_chat_history) as Array<{ role: string; text: string }> | undefined;
        if (Array.isArray(history) && history.length > 0) {
          setChatMessages(
            history.map((entry) => ({
              role: entry.role === "assistant" ? "agent" : (entry.role as ChatMessage["role"]),
              text: entry.text,
            }))
          );
        }
        if (
          !coachApprovedRef.current &&
          (latestStatusRef.current === "coaching" ||
            latestStatusRef.current === "awaiting_coach_review")
        ) {
          setCoachReviewOpen(true);
        }
      }
      if (evt.status && latestStatusRef.current !== "coaching" && latestStatusRef.current !== "awaiting_coach_review") {
        setCoachReviewOpen(false);
      }

      if (evt.event === "shortlist_review" && evt.scored_jobs && latestStatusRef.current === "awaiting_review" && !shortlistApprovedRef.current) {
        const jobs = evt.scored_jobs as ScoredJobData[];
        restoreShortlist(jobs);
        setShortlistReviewOpen(true);
      }
      if (evt.status && latestStatusRef.current !== "tailoring" && latestStatusRef.current !== "awaiting_review") {
        setShortlistReviewOpen(false);
      }

      if (evt.event === "done" && evt.session_summary) {
        setSessionSummary(evt.session_summary);
      }

      if (evt.event === "status" && evt.status === "steering" && evt.message) {
        setChatMessages((prev) => {
          const nextText = String(evt.message || "Steering updated.");
          const last = prev[prev.length - 1];
          if (last?.role === "agent" && last.text === nextText) {
            return prev;
          }
          return [...prev, { role: "agent", text: nextText }];
        });
      }
      if (evt.event === "error" && evt.message) {
        setChatMessages((prev) => [
          ...prev,
          { role: "system", text: evt.message || "An error occurred." },
        ]);
      }

      // Handle agent intervention request
      if (evt.event === "needs_intervention") {
        const d = (evt.data || evt) as Record<string, unknown>;
        if (d.reason) {
          setInterventionData({
            job_id: String(d.job_id || ""),
            job_title: String(d.job_title || "Unknown"),
            company: String(d.company || "Unknown"),
            reason: String(d.reason || "Agent needs help"),
            screenshot: d.screenshot ? String(d.screenshot) : undefined,
          });
        }
      }

      // Handle ready-to-submit confirmation
      if (evt.event === "ready_to_submit") {
        const d = (evt.data || evt) as Record<string, unknown>;
        setSubmitConfirmData({
          job_id: String(d.job_id || ""),
          job_title: String(d.job_title || "Unknown"),
          company: String(d.company || "Unknown"),
          url: String(d.url || ""),
          fields_filled: Number(d.fields_filled || 0),
          screenshot: d.screenshot ? String(d.screenshot) : undefined,
        });
      }

      // Clear intervention/submit confirmation when agent resumes
      if (evt.status === "applying" && evt.message?.includes("resuming")) {
        setInterventionData(null);
      }
      if (
        evt.status === "applying" &&
        (evt.message?.includes("Submitting") || evt.message?.includes("Skipping"))
      ) {
        setSubmitConfirmData(null);
      }

      // Pre-login flow: show login modal when apply agent needs authentication
      if (evt.event === "login_required") {
        const d = (evt.data || evt) as Record<string, unknown>;
        setLoginPrompt({
          board: String(d.board || "unknown"),
          message: String(d.message || "Please log in in the browser window."),
        });
      }
      if (evt.event === "login_complete") {
        setLoginPrompt(null);
      }

    }, (connected) => {
      setSseConnected(connected);
      if (connected) {
        setSseFailCount(0);
      } else {
        setSseFailCount((c) => c + 1);
      }
    });
    return cleanup;
  }, [sessionId, sseKey]);

  const handleSendChat = async (message: string) => {
    const msg = message.trim();
    if (!msg) return;
    const isCoachChatMode = coachReviewOpen || latestStatusRef.current === "awaiting_coach_review";

    setChatMessages((prev) => [...prev, { role: "user", text: msg }]);
    setChatLoading(true);

    try {
      if (isCoachChatMode) {
        const response = await sendCoachChat(sessionId, { message: msg });
        if (response.coach_output) {
          setCoachReviewData(response.coach_output);
          setSession((prev) =>
            prev
              ? {
                  ...prev,
                  coach_output: response.coach_output,
                  coach_chat_history: response.coach_chat_history,
                }
              : prev
          );
          setCoachReviewOpen(true);
        }
        if (response.message) {
          setChatMessages((prev) => [...prev, { role: "agent", text: response.message }]);
        }
        return;
      }

      const response = await sendSteer(sessionId, {
        message: msg,
        mode: "status",
      });
      if (response.message) {
        setChatMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "agent" && last.text === response.message) {
            return prev;
          }
          return [...prev, { role: "agent", text: response.message }];
        });
      }
    } catch (e) {
      console.error("Failed to send steering message:", e);
      setChatMessages((prev) => [
        ...prev,
        { role: "system", text: "Could not send message to the agent." },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleApproveShortlist = async () => {
    setShortlistSubmitting(true);
    try {
      const jobIds = Array.from(selectedJobIds);
      await submitReview(sessionId, { approved_job_ids: jobIds, feedback: "" });
      shortlistApprovedRef.current = true;
      shortlistSelectionInitializedRef.current = false;
      settlingReviewRef.current = "awaiting_review";
      approvalVersionRef.current += 1;
      latestStatusRef.current = "applying";
      setShortlistReviewOpen(false);
      setShortlistSubmitting(false);
      setSession((prev) => (prev ? { ...prev, status: "applying" } : prev));
    } catch (e) {
      console.error("Failed to submit review:", e);
      setShortlistSubmitting(false);
    }
  };

  const toggleJobSelection = (jobId: string) => {
    setSelectedJobIds((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) next.delete(jobId);
      else next.add(jobId);
      return next;
    });
  };

  const handleApproveCoachReview = async (useOriginal = false) => {
    setCoachReviewSubmitting(true);
    try {
      await submitCoachReview(sessionId, { approved: true, use_original: useOriginal });
      coachApprovedRef.current = true;
      settlingReviewRef.current = "awaiting_coach_review";
      approvalVersionRef.current += 1;
      latestStatusRef.current = "discovering";
      setCoachReviewOpen(false);
      setSession((prev) => (prev ? { ...prev, status: "discovering" } : prev));
    } catch (e) {
      console.error("Failed to submit coach review:", e);
    } finally {
      setCoachReviewSubmitting(false);
    }
  };

  const handleResumeIntervention = async () => {
    try {
      await resumeIntervention(sessionId);
      setInterventionData(null);
    } catch (e) {
      console.error("Failed to resume:", e);
    }
  };

  const handleSubmitDecision = async (decision: "submit" | "skip") => {
    try {
      await submitDecision(sessionId, decision);
      setSubmitConfirmData(null);
    } catch (e) {
      console.error("Failed to send submit decision:", e);
    }
  };

  const handleLoadCheckpoints = async () => {
    try {
      const cps = await listCheckpoints(sessionId);
      setCheckpoints(cps);
    } catch (e) {
      console.error("Failed to load checkpoints:", e);
    }
  };

  const handleRewind = async (checkpointId: string) => {
    setRewindLoading(true);
    try {
      await rewindSession(sessionId, checkpointId);
      // Clear stale state from previous run
      setEvents([]);
      setCheckpoints([]);
      setSessionSummary(null);
      setInterventionData(null);
      setSubmitConfirmData(null);
      // Reset approval refs so HITL modals can appear again
      shortlistApprovedRef.current = false;
      shortlistSelectionInitializedRef.current = false;
      settlingReviewRef.current = null;
      approvalVersionRef.current += 1;
      latestStatusRef.current = "applying";
      // Update session status
      setSession((prev) => (prev ? { ...prev, status: "applying" } : prev));
      // Trigger SSE reconnection (old EventSource was closed on "done")
      setSseKey((k) => k + 1);
    } catch (e) {
      console.error("Failed to rewind:", e);
    } finally {
      setRewindLoading(false);
    }
  };

  const sendSuggestedMessage = (message: string) => {
    void handleSendChat(message);
  };

  const surfacedEvents = useMemo(() => compressEvents(events), [events]);
  const liveViewJobLabel = useMemo(() => {
    if (!liveView) return undefined;
    const match = (session?.scored_jobs || []).find((sj) => sj.job.id === liveView.jobId);
    return match ? `${match.job.title} at ${match.job.company}` : undefined;
  }, [liveView, session?.scored_jobs]);

  const quickActions = useMemo(() => {
    if (!session) return [];
    const role = session.keywords?.[0];
    const place = session.remote_only ? "remote" : session.locations?.[0];
    if (coachReviewOpen || session.status === "awaiting_coach_review") {
      return [
        "Explain the biggest changes to my resume",
        role ? `Tighten the resume for ${role} roles` : "Make the summary more specific",
      ];
    }
    if (shortlistReviewOpen || session.status === "awaiting_review") {
      return [
        "Why did these jobs make the shortlist?",
        place ? `Prefer roles in ${place}` : "Prefer larger companies",
      ];
    }
    if (TERMINAL.has(session.status)) {
      const kept = sessionSummary?.total_scored ?? session.scored_jobs?.length ?? 0;
      return kept === 0
        ? ["Which jobs came closest to the cutoff?", "What should I change to get a shortlist?"]
        : ["Summarize what was sent", "Which companies replied fastest last time?"].slice(0, 1);
    }
    if (session.status === "applying" || interventionData || submitConfirmData) {
      return ["What is the agent doing now?", "Skip the next job"];
    }
    return [
      "What is the agent doing now?",
      role ? `Only ${role} titles, no adjacent roles` : "Skip contract roles",
    ];
  }, [coachReviewOpen, interventionData, session, sessionSummary, shortlistReviewOpen, submitConfirmData]);

  const [stopOpen, setStopOpen] = useState(false);
  const [runAction, setRunAction] = useState<"pause" | "resume" | "stop" | "rerun" | null>(null);
  const [rerunOpen, setRerunOpen] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [needsDismissed, setNeedsDismissed] = useState<string | null>(null);

  const handleStop = async () => {
    setRunAction("stop");
    try {
      await killSession(sessionId);
      approvalVersionRef.current += 1;
      latestStatusRef.current = "failed";
      setCoachReviewOpen(false);
      setShortlistReviewOpen(false);
      setStopOpen(false);
      toast("Run stopped. Applications already sent are kept.");
      setSession((prev) => (prev ? { ...prev, status: "failed" } : prev));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't stop the run.");
    } finally {
      setRunAction(null);
    }
  };

  const handlePause = async () => {
    setRunAction("pause");
    try {
      await sendSteer(sessionId, { message: "Pause after the current step", mode: "status" });
      toast("The agent will pause after its current step.");
    } catch {
      toast.error("Couldn't reach the agent. Try again in a moment.");
    } finally {
      setRunAction(null);
    }
  };

  const handleResumeRun = async () => {
    setRunAction("resume");
    try {
      await resumeSession(sessionId);
      setSseKey((k) => k + 1);
    } catch {
      toast.error("Couldn't resume the run. Try again in a moment.");
    } finally {
      setRunAction(null);
    }
  };

  const handleRerun = async (overrides?: RunOverrides) => {
    setRunAction("rerun");
    try {
      const { session_id } = await rerunSession(sessionId, overrides);
      window.location.href = `/session/${session_id}`;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't start the run.");
      setRunAction(null);
    }
  };

  // ---- Ledger counts, from the most reliable source available ----
  const discoveredFromEvents = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      if (typeof events[i].jobs_found === "number") return events[i].jobs_found as number;
    }
    return null;
  }, [events]);

  if (!session) {
    return (
      <div className="space-y-5" aria-busy="true">
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex gap-3">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="flex-1 space-y-2">
                <div className="h-3 w-16 rounded bg-muted" />
                <div className="h-5 w-10 rounded bg-muted" />
                <div className="h-1.5 rounded-full bg-muted" />
              </div>
            ))}
          </div>
        </div>
        <div className="h-64 rounded-xl border border-border bg-card" />
      </div>
    );
  }

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
  const attempted = finished ? submittedCount + failedCount + uncertainCount + skippedCount : session.applications_used || null;
  const threshold = scoreThreshold(session.session_config as { scoring_strictness?: unknown; discovery_mode?: unknown });
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
      if (!last || !session.created_at) return null;
      return (new Date(last).getTime() - new Date(session.created_at).getTime()) / 60000;
    })();

  const finishedReason = (() => {
    if (uncertainCount > 0) return "Confirmation pending—check before retrying";
    if (submittedCount > 0)
      return failedCount > 0 ? `${submittedCount} sent, ${failedCount} failed` : `${submittedCount} sent`;
    if (found === 0) return "no postings matched your roles and location";
    if (shortlisted === 0) return session.session_config?.discovery_mode === "manual_urls" ? "no job links were selected" : "no jobs met your score threshold";
    if (questionCount > 0) return `${questionCount} ${questionCount === 1 ? "application needs" : "applications need"} your answers · nothing sent`;
    if (queuedEmployerCount > 0) return `${queuedEmployerCount} employer ${queuedEmployerCount === 1 ? "application" : "applications"} queued · nothing sent`;
    if (skippedCount > 0) return `${skippedCount} skipped${failedCount > 0 ? `, ${failedCount} failed` : ""} · nothing sent`;
    if (failedCount > 0) return "every application failed";
    return "you didn't approve any jobs";
  })();

  const elapsedLabel = `${elapsedMin}:${elapsedSec.toString().padStart(2, "0")}`;
  const stateLine =
    status === "completed"
      ? `Finished${durationMin != null ? ` in ${formatDuration(durationMin)}` : ""} · ${finishedReason}`
      : status === "failed"
      ? uncertainCount > 0 ? "Stopped · Confirmation pending—check before retrying" : `Stopped${submittedCount > 0 ? ` · ${submittedCount} sent before it stopped` : " · nothing was sent"}`
      : status === "awaiting_coach_review"
      ? "Waiting for you to approve your resume"
      : status === "awaiting_review"
      ? `Waiting for your approval · ${shortlistJobs.length || session.scored_jobs?.length || 0} jobs on the shortlist`
      : status === "paused"
      ? "Paused · resume when you're ready"
      : `${STATUS_LABELS[status] ?? "Running"} · running ${elapsedLabel}`;

  const stateTone: OutcomeTone = finished
    ? runOutcome({ status, submitted: submittedCount, failed: failedCount, uncertain: uncertainCount }).tone
    : NEEDS_YOU.has(status) || interventionData || submitConfirmData || loginPrompt
    ? "needs"
    : "running";

  // The one thing the user can do next. A run that sent nothing never offers "success".
  const shortlistCount = shortlistJobs.length || session.scored_jobs?.length || 0;
  const primary: { label: string; onClick: () => void } | null =
    status === "awaiting_coach_review"
      ? { label: "Review resume", onClick: () => setCoachReviewOpen(true) }
      : status === "awaiting_review"
      ? { label: `Review shortlist · ${shortlistCount} jobs`, onClick: () => setShortlistReviewOpen(true) }
      : interventionData
      ? { label: "Resume agent", onClick: () => void handleResumeIntervention() }
      : status === "paused"
      ? { label: "Resume run", onClick: () => void handleResumeRun() }
      : finished && uncertainCount > 0
      ? null
      : finished && submittedCount === 0
      ? { label: "Adjust search", onClick: () => setAdjustOpen(true) }
      : finished
      ? { label: "Run again", onClick: () => setRerunOpen(true) }
      : null;

  // Needs-you bar: the open gate or intervention, pinned under the header.
  const needs: { key: string; text: React.ReactNode; actions: React.ReactNode } | null = submitConfirmData
    ? {
        key: `submit-${submitConfirmData.job_id}`,
        text: (
          <>
            <strong className="font-semibold">Ready to submit {submitConfirmData.job_title}</strong> at{" "}
            {submitConfirmData.company}. {submitConfirmData.fields_filled} fields filled. Check the form, then
            submit or skip.
          </>
        ),
        actions: (
          <>
            <Button size="sm" variant="outline" onClick={() => void handleSubmitDecision("skip")}>
              Skip
            </Button>
            <Button size="sm" onClick={() => void handleSubmitDecision("submit")}>
              Submit application
            </Button>
          </>
        ),
      }
    : interventionData
    ? {
        key: `help-${interventionData.job_id}`,
        text: (
          <>
            <strong className="font-semibold">
              {interventionData.job_title} at {interventionData.company} needs your help.
            </strong>{" "}
            {interventionData.reason} Fix it in the browser{liveView ? " below" : ""}, then resume.
          </>
        ),
        actions: (
          <Button size="sm" onClick={() => void handleResumeIntervention()}>
            Resume agent
          </Button>
        ),
      }
    : status === "awaiting_review"
    ? {
        key: "shortlist",
        text: (
          <>
            <strong className="font-semibold">Shortlist waiting for you.</strong> {shortlistCount}{" "}
            {shortlistCount === 1 ? "job" : "jobs"} passed your filters. Nothing is sent until you approve.
          </>
        ),
        actions: (
          <Button size="sm" onClick={() => setShortlistReviewOpen(true)}>
            Review {shortlistCount} {shortlistCount === 1 ? "job" : "jobs"}
          </Button>
        ),
      }
    : status === "awaiting_coach_review"
    ? {
        key: "coach",
        text: (
          <>
            <strong className="font-semibold">Your coached resume is ready.</strong> Approve it, or keep your
            original, before the search starts.
          </>
        ),
        actions: (
          <Button size="sm" onClick={() => setCoachReviewOpen(true)}>
            Review resume
          </Button>
        ),
      }
    : null;

  // Event log: deduplicated, grouped by phase, with time since the run started.
  const startMs = session.created_at ? new Date(session.created_at).getTime() : null;
  const logRows = (() => {
    const seen = new Set<string>();
    const rows: { group: PhaseKey; t: string; step: string; text: string; tone: "default" | "error" | "needs" }[] = [];
    let group: PhaseKey = "resume";
    for (const evt of surfacedEvents) {
      const agent = (evt.event?.endsWith("_progress") ? evt.event.replace("_progress", "") : evt.agent || evt.event || "system") as string;
      const text = pipelineEventText(evt);
      if (!text) continue;
      const key = `${agent}|${text}|${evt.timestamp ?? ""}`;
      if (seen.has(key)) continue;
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

  const showNeeds = needs && needsDismissed !== needs.key;

  return (
    <>
      <section aria-label="Run status" className="rounded-xl border border-border bg-card px-5 pt-5">
        <PipelineLedger phases={ledger.phases} gates={ledger.gates} />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-border py-3">
          <p className="flex min-w-0 items-center gap-2 text-sm" aria-live="polite">
            <StatusDot tone={stateTone} className="text-foreground">
              <span className="text-foreground">{stateLine}</span>
            </StatusDot>
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {running && (
              <>
                <Button size="sm" variant="outline" loading={runAction === "pause"} onClick={() => void handlePause()}>
                  Pause
                </Button>
                <Button size="sm" variant="outline" className="text-destructive" onClick={() => setStopOpen(true)}>
                  Stop run
                </Button>
              </>
            )}
            {finished && submittedCount === 0 && (
              <Button size="sm" variant="outline" onClick={() => setRerunOpen(true)}>
                Run again
              </Button>
            )}
            {primary && (
              <Button size="sm" onClick={primary.onClick}>
                {primary.label}
              </Button>
            )}
          </div>
        </div>
      </section>

      {showNeeds && needs && (
        <div
          role="status"
          className="sticky top-14 z-30 mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-warning-border bg-warning-surface px-4 py-3 text-sm text-warning lg:top-2"
        >
          <p className="min-w-0 flex-1 basis-72">{needs.text}</p>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="ghost"
              className="text-warning hover:bg-warning-border/30"
              onClick={() => {
                setNeedsDismissed(needs.key);
                toast("It will wait for you on Home.");
              }}
            >
              Not now
            </Button>
            {needs.actions}
          </div>
        </div>
      )}

      {!sseConnected && !finished && (
        <p className="mt-3 rounded-xl border border-border bg-card px-4 py-2.5 text-sm" role="status">
          {sseFailCount >= 5 ? (
            <>
              Lost the live connection. The run continues in the background.{" "}
              <button type="button" className="font-medium text-primary underline" onClick={() => window.location.reload()}>
                Reload
              </button>
            </>
          ) : (
            "Reconnecting to the live log…"
          )}
        </p>
      )}

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-5">
          {liveView && (
            <LiveBrowserPanel liveView={liveView} jobLabel={liveViewJobLabel} onHide={() => setLiveView(null)} />
          )}

          <ApplicationFollowups questions={session.application_questions} employers={session.employer_application_queue} savedRules={savedAnswerRules} onAnswer={async (jobId, answer) => {
            const question = session.application_questions?.[jobId];
            if (!question) throw new Error("This question is no longer available. Reload the run.");
            await saveAnswer(question, answer);
            return {};
          }} />

          <section aria-labelledby="log-h" className="overflow-hidden rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 id="log-h" className="text-base font-semibold">
                Activity
              </h2>
              <span className="font-mono text-xs text-muted-foreground">
                {logRows.length} {logRows.length === 1 ? "event" : "events"}
              </span>
            </div>
            {logRows.length === 0 ? (
              <p className="px-4 py-8 text-sm text-muted-foreground">
                {finished ? "This run has no saved activity." : "Waiting for the first update from the agent."}
              </p>
            ) : (
              <div role="log" aria-live="polite" aria-label="Run activity">
                <table className="w-full border-collapse text-[13px]">
                  <tbody>
                    {logRows.map((r, i) => {
                      const head = i === 0 || logRows[i - 1].group !== r.group;
                      return (
                        <Fragment key={i}>
                          {head && (
                            <tr className="border-t border-border bg-surface-2 first:border-t-0">
                              <th colSpan={3} scope="colgroup" className="px-4 py-2 text-left font-medium text-muted-foreground">
                                {PHASES.find((p) => p.key === r.group)?.label}
                              </th>
                            </tr>
                          )}
                          <tr className="border-t border-border align-top max-sm:flex max-sm:flex-wrap max-sm:px-4 max-sm:py-2.5">
                            <td className="w-16 whitespace-nowrap py-2.5 pl-4 pr-2 font-mono text-muted-foreground max-sm:w-auto max-sm:p-0 max-sm:pr-2">
                              {r.t}
                            </td>
                            <td className="w-24 py-2.5 pr-2 text-muted-foreground max-sm:w-auto max-sm:p-0">{r.step}</td>
                            <td
                              className={cn(
                                "py-2.5 pr-4 max-sm:basis-full max-sm:p-0 max-sm:pt-0.5",
                                r.tone === "error" ? "text-destructive" : r.tone === "needs" ? "text-warning" : "text-foreground"
                              )}
                            >
                              {r.text}
                            </td>
                          </tr>
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {session.applications_submitted && session.applications_submitted.length > 0 && (
            <section aria-labelledby="sent-h" className="rounded-xl border border-border bg-card">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <h2 id="sent-h" className="text-base font-semibold">
                  Sent
                </h2>
                <Link href={`/session/${sessionId}/manual-apply`} className="text-[13px] font-medium text-primary hover:underline">
                  All applications
                </Link>
              </div>
              <ul className="divide-y divide-border text-[13px]">
                {session.applications_submitted.map((app, i) => (
                  <li key={i} className="flex items-center gap-2 px-4 py-2.5">
                    <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full bg-primary" />
                    <span className="min-w-0 flex-1 truncate">
                      {app.job?.title && app.job?.company ? `${app.job.title} at ${app.job.company}` : "Application"}
                    </span>
                    <span className="text-muted-foreground">{app.status === "submitted" ? "Submitted" : app.status}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <aside className="min-w-0 space-y-5" aria-label="Run details">
          {(submitConfirmData || interventionData || loginPrompt) && (
            <section aria-labelledby="queue-h" className="rounded-xl border border-warning-border bg-card p-4">
              <h2 id="queue-h" className="text-base font-semibold">
                Needs you
              </h2>
              <ul className="mt-2 space-y-3 text-sm">
                {submitConfirmData && (
                  <li>
                    <p>
                      Submit {submitConfirmData.job_title} at {submitConfirmData.company}?
                    </p>
                    <div className="mt-2 flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => void handleSubmitDecision("skip")}>
                        Skip
                      </Button>
                      <Button size="sm" onClick={() => void handleSubmitDecision("submit")}>
                        Submit
                      </Button>
                    </div>
                  </li>
                )}
                {interventionData && (
                  <li className="text-warning">
                    {interventionData.job_title}: {interventionData.reason}
                  </li>
                )}
                {loginPrompt && <li>Sign in to {loginPrompt.board} in the browser window.</li>}
              </ul>
            </section>
          )}

          <section aria-labelledby="params-h" className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-baseline justify-between">
              <h2 id="params-h" className="text-base font-semibold">
                Parameters
              </h2>
              {finished && (
                <button type="button" onClick={() => setAdjustOpen(true)} className="text-[13px] font-medium text-primary hover:underline">
                  Adjust
                </button>
              )}
            </div>
            <dl className="mt-3 grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-2.5 text-[13px]">
              <dt className="text-muted-foreground">Roles</dt>
              <dd className="flex flex-wrap gap-1">
                {(session.keywords ?? []).map((kw) => (
                  <Badge key={kw} variant="secondary" className="font-normal">
                    {kw}
                  </Badge>
                ))}
              </dd>
              <dt className="text-muted-foreground">Location</dt>
              <dd>{session.remote_only ? "Remote only" : session.locations?.join(", ") || "Anywhere"}</dd>
              {session.salary_min != null && session.salary_min > 0 && (
                <>
                  <dt className="text-muted-foreground">Salary floor</dt>
                  <dd className="font-mono">${session.salary_min.toLocaleString()}</dd>
                </>
              )}
              {threshold != null && (
                <>
                  <dt className="text-muted-foreground">Score cutoff</dt>
                  <dd className="font-mono">{threshold}</dd>
                </>
              )}
              <dt className="text-muted-foreground">Approval</dt>
              <dd>
                {session.session_config?.discovery_mode === "manual_urls"
                  ? "You approved these job links in Quick Apply"
                  : "You approve the shortlist before anything is sent"}
              </dd>
              <dt className="text-muted-foreground">Credit estimate</dt>
              <dd>
                <span className="font-mono">{uncertainCount > 0 ? "Pending confirmation" : submittedCount + failedCount * 0.5}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  Before free applications or plan coverage. <Link href="/billing" className="underline">View actual charges</Link>.
                </span>
              </dd>
              {session.coach_output?.resume_score && (
                <>
                  <dt className="text-muted-foreground">Resume</dt>
                  <dd>
                    <span className="font-mono">{session.coach_output.resume_score.overall} / 100</span>
                    {session.coach_output.confidence_message && (
                      <span className="mt-0.5 block text-muted-foreground">
                        {session.coach_output.confidence_message}
                      </span>
                    )}
                    {session.coach_output && (
                      <button
                        type="button"
                        onClick={() => {
                          setCoachReviewData(session.coach_output as CoachOutput);
                          setCoachReviewOpen(true);
                        }}
                        className="mt-0.5 font-medium text-primary hover:underline"
                      >
                        Full report
                      </button>
                    )}
                  </dd>
                </>
              )}
            </dl>
            {session.session_config?.discovery_mode === "manual_urls" &&
              (session.session_config?.job_urls?.length || session.job_urls?.length) && (
                <QuickApplyUrls
                  urls={session.session_config?.job_urls || session.job_urls || []}
                  submitted={submittedCount}
                  failed={failedCount + uncertainCount}
                />
              )}
          </section>

          <section aria-labelledby="chat-h" className="overflow-hidden rounded-xl border border-border bg-card">
            <div className="px-4 pt-4">
              <h2 id="chat-h" className="text-base font-semibold">
                {finished ? "Ask about this run" : "Guide the agent"}
              </h2>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {quickActions.map((action) => (
                  <button
                    key={action}
                    type="button"
                    onClick={() => sendSuggestedMessage(action)}
                    className="rounded-full border border-border bg-card px-3 py-1 text-left text-[13px] text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5"
                  >
                    {action}
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-3 h-64">
              <ChatPanel
                emptyText={
                  finished
                    ? "Answers come from this run's log and results."
                    : "The agent reads your message before its next step."
                }
                messages={chatMessages}
                onSend={handleSendChat}
                disabled={false}
                isLoading={chatLoading}
                placeholder={
                  coachReviewOpen || latestStatusRef.current === "awaiting_coach_review"
                    ? "Ask the coach to change your resume"
                    : finished
                    ? "Ask why a job was removed"
                    : "Tell the agent what to change"
                }
              />
            </div>
          </section>

          {finished && (
            <section aria-labelledby="cp-h" className="rounded-xl border border-border bg-card p-4">
              <h2 id="cp-h" className="text-base font-semibold">
                Checkpoints
              </h2>
              <p className="mt-1 text-[13px] text-muted-foreground">
                Pick up from an approval step instead of starting over.
              </p>
              {checkpoints.length === 0 ? (
                <Button size="sm" variant="outline" className="mt-3" onClick={handleLoadCheckpoints}>
                  Show checkpoints
                </Button>
              ) : (
                <ul className="mt-3 space-y-2">
                  {checkpoints
                    .filter((cp) => ["paused", "awaiting_review", "awaiting_coach_review"].includes(cp.status))
                    .map((cp) => (
                      <li key={cp.checkpoint_id} className="flex items-center justify-between gap-2 text-[13px]">
                        <span>
                          {checkpointLabel(cp.status)}
                          <span className="ml-1.5 font-mono text-muted-foreground">{cp.application_queue} queued</span>
                        </span>
                        <Button size="sm" variant="outline" disabled={rewindLoading} onClick={() => handleRewind(cp.checkpoint_id)}>
                          Rewind
                        </Button>
                      </li>
                    ))}
                  {checkpoints.filter((cp) => ["paused", "awaiting_review", "awaiting_coach_review"].includes(cp.status)).length === 0 && (
                    <li className="text-[13px] text-muted-foreground">No approval steps to rewind to.</li>
                  )}
                </ul>
              )}
            </section>
          )}
        </aside>
      </div>

      <Dialog open={stopOpen} onOpenChange={setStopOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Stop this run?</DialogTitle>
            <DialogDescription>
              The agent stops after its current step. Applications already sent stay sent, and you aren&apos;t
              charged for jobs it didn&apos;t reach.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setStopOpen(false)}>
              Keep running
            </Button>
            <Button variant="destructive" loading={runAction === "stop"} onClick={() => void handleStop()}>
              Stop run
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={rerunOpen} onOpenChange={setRerunOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Run this search again</DialogTitle>
            <DialogDescription>
              Same roles and location. You approve the shortlist before anything is sent. Each application sent
              costs 1 credit.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRerunOpen(false)}>
              Cancel
            </Button>
            <Button loading={runAction === "rerun"} onClick={() => void handleRerun()}>
              Start run
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {adjustOpen && (
        <AdjustDialog
          run={session}
          busy={runAction === "rerun"}
          costLine="You approve the shortlist before anything is sent. Each application sent costs 1 credit."
          onCancel={() => setAdjustOpen(false)}
          onStart={(o) => void handleRerun(o)}
        />
      )}

      {/* Resume approval (gate 1) */}
      <Dialog open={coachReviewOpen} onOpenChange={setCoachReviewOpen}>
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {session.status === "awaiting_coach_review" ? "Approve your coached resume" : "Resume report"}
            </DialogTitle>
            <DialogDescription>
              {session.status === "awaiting_coach_review"
                ? "The coach rewrote your resume. Approve it to start the search, or keep your original."
                : "What the coach changed and why. This run used the approved version."}
            </DialogDescription>
          </DialogHeader>
          {coachReviewData && (
            <div className="space-y-4">
              <CoachPanel coach={coachReviewData} />
              {session.status === "awaiting_coach_review" && (
                <section className="overflow-hidden rounded-xl border border-border">
                  <h3 className="border-b border-border px-4 py-2.5 text-sm font-semibold">Ask the coach</h3>
                  <div className="h-56">
                    <ChatPanel
                      messages={chatMessages}
                      onSend={handleSendChat}
                      disabled={false}
                      isLoading={chatLoading}
                      placeholder="Ask the coach to change your resume"
                    />
                  </div>
                </section>
              )}
            </div>
          )}
          <DialogFooter className="gap-2 sm:gap-0">
            {session.status === "awaiting_coach_review" ? (
              <>
                <Button variant="ghost" onClick={() => setCoachReviewOpen(false)} disabled={coachReviewSubmitting}>
                  Not now
                </Button>
                <Button variant="outline" onClick={() => handleApproveCoachReview(true)} disabled={coachReviewSubmitting}>
                  Keep my original
                </Button>
                <Button onClick={() => handleApproveCoachReview()} loading={coachReviewSubmitting}>
                  Approve and search
                </Button>
              </>
            ) : (
              <Button variant="outline" onClick={() => setCoachReviewOpen(false)}>
                Close
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Shortlist approval (gate 2) */}
      <Dialog open={shortlistReviewOpen} onOpenChange={setShortlistReviewOpen}>
        <DialogContent className="flex max-h-[85vh] max-w-3xl flex-col">
          <DialogHeader>
            <DialogTitle>Approve the shortlist</DialogTitle>
            <DialogDescription>
              Untick any job you don&apos;t want. Only the jobs you approve are sent, at 1 credit each.
            </DialogDescription>
          </DialogHeader>
          <fieldset className="-mx-1 min-h-0 flex-1 space-y-2 overflow-y-auto px-1 py-1">
            <legend className="sr-only">Jobs on the shortlist</legend>
            {shortlistJobs.map((sj) => {
              const selected = selectedJobIds.has(sj.job.id);
              const companyKey = sj.job.company.toLowerCase().trim();
              const isDuplicateCompany = selected && (selectedCompanyCounts.get(companyKey) || 0) > 1;
              return (
                <label
                  key={sj.job.id}
                  className={cn(
                    "flex cursor-pointer gap-3 rounded-xl border p-4 transition-colors",
                    selected ? "border-primary/40 bg-primary/5" : "border-border hover:bg-surface-2"
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={() => toggleJobSelection(sj.job.id)}
                    className="mt-0.5 h-4 w-4 shrink-0 accent-[hsl(var(--primary))]"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-baseline justify-between gap-x-3">
                      <span className="text-sm font-medium">{sj.job.title}</span>
                      <span className="font-mono text-sm">
                        {sj.score}
                        <span className="text-muted-foreground"> / 100</span>
                      </span>
                    </span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                      {sj.job.company} · {sj.job.location}
                      <Badge variant="secondary" className="font-normal capitalize">
                        {sj.job.board}
                      </Badge>
                      {isDuplicateCompany && (
                        <Badge variant="warning" className="font-normal">
                          Only 1 per company is sent
                        </Badge>
                      )}
                    </span>
                    {sj.fit_summary && (
                      <span className="mt-2 block text-xs leading-relaxed text-muted-foreground">{sj.fit_summary}</span>
                    )}
                  </span>
                </label>
              );
            })}
          </fieldset>
          <DialogFooter className="flex-col items-stretch gap-2 sm:flex-row sm:items-center sm:justify-between">
            <span className="font-mono text-sm text-muted-foreground">
              {selectedJobIds.size} of {shortlistJobs.length} selected
            </span>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setShortlistReviewOpen(false)} disabled={shortlistSubmitting}>
                Not now
              </Button>
              <Button onClick={handleApproveShortlist} loading={shortlistSubmitting} disabled={selectedJobIds.size === 0}>
                Approve {selectedJobIds.size} {selectedJobIds.size === 1 ? "job" : "jobs"}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Pre-login modal */}
      <Dialog open={!!loginPrompt} onOpenChange={() => {}}>
        <DialogContent className="sm:max-w-md" onInteractOutside={(e) => e.preventDefault()}>
          <DialogHeader>
            <DialogTitle>
              Sign in to {loginPrompt?.board?.replace(/^\w/, (c) => c.toUpperCase())}
            </DialogTitle>
            <DialogDescription>{loginPrompt?.message}</DialogDescription>
          </DialogHeader>
          <div className="bg-muted/50 rounded p-3 text-sm text-muted-foreground">
            A browser window is open on the sign-in page. Sign in with your account, then continue.
          </div>
          <DialogFooter>
            <Button
              onClick={async () => {
                setLoginConfirming(true);
                try {
                  await confirmLogin(sessionId);
                  setLoginPrompt(null);
                } catch (e) {
                  console.error("Failed to confirm login:", e);
                } finally {
                  setLoginConfirming(false);
                }
              }}
              loading={loginConfirming}
            >
              I&apos;ve signed in, continue
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
