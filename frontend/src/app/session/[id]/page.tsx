"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CircularProgress } from "@/components/ui/circular-progress";
import { ChatPanel, type ChatMessage } from "@/components/ChatPanel";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { CoachPanel } from "@/components/CoachPanel";
import { TakeoverViewer } from "@/components/TakeoverViewer";
import {
  LinkedInUpdateButton,
  type LinkedInProgress,
} from "@/components/LinkedInUpdateButton";
import {
  getSession,
  connectSSE,
  sendSteer,
  sendCoachChat,
  submitReview,
  submitCoachReview,
  resumeIntervention,
  submitDecision,
  listCheckpoints,
  rewindSession,
  resumeSession,
  confirmLogin,
} from "@/lib/api";
import type { Checkpoint } from "@/lib/api";
import type { CoachOutput } from "@/lib/api";
import { WebSocketManager } from "@/lib/websocket";

type SessionData = {
  session_summary?: boolean;
  session_id: string;
  status: string;
  pause_resume_node?: string | null;
  status_before_pause?: string | null;
  keywords: string[];
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
    job_id: string;
    status: string;
    submitted_at?: string;
  }>;
  applications_failed: Array<{
    job_id: string;
    error_message?: string;
  }>;
  coach_output?: CoachOutput;
  coach_chat_history?: Array<{ role: string; text: string }>;
  linkedin_url?: string;
  steering_mode: string;
  applications_used: number;
  applications_skipped: string[] | number;
};

type SessionSummaryData = {
  session_id: string;
  total_discovered: number;
  total_scored: number;
  total_applied: number;
  total_failed: number;
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
};

type SSEEvent = {
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

type WebSocketStatus = "connecting" | "connected" | "disconnected" | "error";

const STATUS_LABELS: Record<string, string> = {
  intake: "Setting Up",
  coaching: "Coaching Resume",
  awaiting_coach_review: "Review Your Resume",
  discovering: "Finding Jobs",
  scoring: "Ranking Matches",
  tailoring: "Customizing Resumes",
  awaiting_review: "Your Turn to Review",
  applying: "Submitting Applications",
  verifying: "Checking Results",
  reporting: "Preparing Summary",
  paused: "Paused",
  needs_intervention: "Needs Your Help",
  takeover: "Manual Control",
  completed: "All Done",
  failed: "Something Went Wrong",
};

const PIPELINE_STEPS = [
  "intake",
  "coaching",
  "awaiting_coach_review",
  "discovering",
  "scoring",
  "tailoring",
  "awaiting_review",
  "applying",
  "verifying",
  "reporting",
  "completed",
];

function normalizeScreenshotSrc(image: string): string {
  if (!image) return image;
  return image.startsWith("data:") ? image : `data:image/jpeg;base64,${image}`;
}

const STEP_LABELS: Record<string, string> = {
  intake: "Setup",
  coaching: "Coach",
  awaiting_coach_review: "Review",
  discovering: "Search",
  scoring: "Rank",
  tailoring: "Tailor",
  awaiting_review: "Review",
  applying: "Apply",
  verifying: "Verify",
  reporting: "Summary",
  completed: "Done",
};

const AGENT_DISPLAY_NAMES: Record<string, string> = {
  intake: "Setup",
  career_coach: "Coach",
  coaching: "Coach",
  discovery: "Search",
  scoring: "Ranking",
  resume_tailor: "Tailor",
  tailoring: "Tailor",
  application: "Apply",
  verification: "Verify",
  reporting: "Summary",
  status: "Status",
  system: "System",
};

const AGENT_COLORS: Record<string, string> = {
  intake:
    "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800",
  career_coach:
    "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950 dark:text-purple-300 dark:border-purple-800",
  coaching:
    "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950 dark:text-purple-300 dark:border-purple-800",
  discovery:
    "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800",
  scoring:
    "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800",
  resume_tailor:
    "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-950 dark:text-orange-300 dark:border-orange-800",
  application:
    "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950 dark:text-rose-300 dark:border-rose-800",
  verification:
    "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-950 dark:text-teal-300 dark:border-teal-800",
  reporting:
    "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800",
  status:
    "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-950 dark:text-slate-300 dark:border-slate-800",
  system:
    "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-950 dark:text-slate-300 dark:border-slate-800",
};

function getStepIndexForStatus(
  status: string,
  session?: Pick<SessionData, "pause_resume_node" | "status_before_pause">,
): number {
  const directIndex = PIPELINE_STEPS.indexOf(status);
  if (directIndex >= 0) return directIndex;

  if (status === "needs_intervention" || status === "takeover") {
    return PIPELINE_STEPS.indexOf("applying");
  }
  if (status === "paused") {
    const resumeTarget =
      session?.pause_resume_node || session?.status_before_pause;
    if (resumeTarget) {
      const resumeIndex = PIPELINE_STEPS.indexOf(resumeTarget);
      if (resumeIndex >= 0) return resumeIndex;
    }
    return PIPELINE_STEPS.indexOf("applying");
  }
  return 0;
}

function compressEvents(events: SSEEvent[]): SSEEvent[] {
  const compressed: SSEEvent[] = [];

  for (const event of events) {
    const summary = String(
      event.step || event.message || event.status || event.event || "",
    );
    const signature = [event.event, event.agent || "", summary.trim()].join(
      "|",
    );
    const previous = compressed[compressed.length - 1];
    const previousSummary = previous
      ? String(
          previous.step ||
            previous.message ||
            previous.status ||
            previous.event ||
            "",
        )
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
      return "Coach Review";
    case "awaiting_review":
      return "Shortlist Review";
    case "paused":
      return "Paused Run";
    default:
      return STATUS_LABELS[status] || status;
  }
}

export default function SessionPage() {
  const params = useParams();
  const sessionId = params.id as string;

  const [session, setSession] = useState<SessionData | null>(null);
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [coachReviewOpen, setCoachReviewOpen] = useState(false);
  const [coachReviewData, setCoachReviewData] = useState<CoachOutput | null>(
    null,
  );
  const [coachReviewSubmitting, setCoachReviewSubmitting] = useState(false);
  const [shortlistReviewOpen, setShortlistReviewOpen] = useState(false);
  const [shortlistJobs, setShortlistJobs] = useState<ScoredJobData[]>([]);
  const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());
  const [shortlistSubmitting, setShortlistSubmitting] = useState(false);
  const [stepProgress, setStepProgress] = useState(0);
  const [sessionSummary, setSessionSummary] =
    useState<SessionSummaryData | null>(null);
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
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [rewindLoading, setRewindLoading] = useState(false);
  const [resumeLoading, setResumeLoading] = useState(false);
  const [sseKey, setSseKey] = useState(0);
  const [linkedinProgress, setLinkedinProgress] =
    useState<LinkedInProgress | null>(null);
  const [loginPrompt, setLoginPrompt] = useState<{
    board: string;
    message: string;
  } | null>(null);
  const [loginConfirming, setLoginConfirming] = useState(false);
  const [liveBrowserImage, setLiveBrowserImage] = useState<string | null>(null);
  const [liveBrowserUrl, setLiveBrowserUrl] = useState("");
  const [takeoverActive, setTakeoverActive] = useState(false);
  const [takeoverMessage, setTakeoverMessage] = useState<string | null>(null);
  const [takeoverWsStatus, setTakeoverWsStatus] =
    useState<WebSocketStatus>("connecting");

  const eventsEndRef = useRef<HTMLDivElement>(null);
  const wsManagerRef = useRef<WebSocketManager | null>(null);
  const latestStatusRef = useRef("intake");
  const coachApprovedRef = useRef(false);
  const shortlistApprovedRef = useRef(false);

  // Elapsed timer
  const [sessionStartTime] = useState(() => Date.now());
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  useEffect(() => {
    if (session?.status === "completed" || session?.status === "failed") return;
    const interval = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - sessionStartTime) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [sessionStartTime, session?.status]);
  const elapsedMin = Math.floor(elapsedSeconds / 60);
  const elapsedSec = elapsedSeconds % 60;
  useEffect(() => {
    getSession(sessionId)
      .then((data) => {
        const s = data as unknown as SessionData;
        setSession(s);
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
        const pastShortlist = [
          "applying",
          "verifying",
          "reporting",
          "completed",
          "failed",
        ];
        if (pastCoach.includes(s.status)) coachApprovedRef.current = true;
        if (pastShortlist.includes(s.status))
          shortlistApprovedRef.current = true;

        // Restore modals from persisted state on page reload
        if (s.status === "awaiting_coach_review" && s.coach_output) {
          setCoachReviewData(s.coach_output as unknown as CoachOutput);
          setCoachReviewOpen(true);
          if (
            Array.isArray(s.coach_chat_history) &&
            s.coach_chat_history.length > 0
          ) {
            setChatMessages(
              s.coach_chat_history.map((entry) => ({
                role:
                  entry.role === "assistant"
                    ? "agent"
                    : (entry.role as ChatMessage["role"]),
                text: entry.text,
              })),
            );
          }
        }
        if (
          s.status === "awaiting_review" &&
          s.scored_jobs &&
          s.scored_jobs.length > 0
        ) {
          const jobs = s.scored_jobs as ScoredJobData[];
          setShortlistJobs(jobs);
          setSelectedJobIds(new Set(jobs.map((sj) => sj.job.id)));
          setShortlistReviewOpen(true);
        }
        if (s.status === "completed" && s.session_summary) {
          setSessionSummary(s.session_summary as unknown as SessionSummaryData);
        }
      })
      .catch(() => {
        setSession({
          session_id: sessionId,
          status: "intake",
          keywords: [],
          scored_jobs: [],
          applications_submitted: [],
          applications_failed: [],
          steering_mode: "status",
          applications_used: 0,
          applications_skipped: 0,
        });
      });
  }, [sessionId]);

  useEffect(() => {
    const cleanup = connectSSE(sessionId, (event) => {
      const evt = event as unknown as SSEEvent;
      if (evt.event === "ping") return;

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
        evt.event?.endsWith("_progress") &&
        typeof evt.progress === "number"
      ) {
        setStepProgress(evt.progress);
      }

      if (
        evt.status &&
        (evt.event === "status" ||
          evt.event === "done" ||
          evt.event === "coach_review" ||
          evt.event === "shortlist_review")
      ) {
        latestStatusRef.current = evt.status;
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
          // Prevent SSE replay from regressing the pipeline status backwards
          const prevIdx = PIPELINE_STEPS.indexOf(prev.status);
          const nextIdx = PIPELINE_STEPS.indexOf(evt.status);
          if (nextIdx >= prevIdx || nextIdx === -1 || evt.event === "done") {
            updates.status = evt.status;
            setStepProgress(0);
          }
        }
        if (evt.coach_output)
          updates.coach_output =
            evt.coach_output as unknown as SessionData["coach_output"];
        if (Array.isArray(evt.keywords) && evt.keywords.length > 0)
          updates.keywords = evt.keywords;
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
        // Track application counts from progress events
        if (evt.event === "application_progress") {
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
        return { ...prev, ...updates };
      });

      // Re-fetch full session on status changes to sync sidebar
      // Only refetch on terminal events or significant status changes — not
      // during replay of historical events (which would flood the API and
      // cause status oscillation between historical and current values).
      if (
        evt.event === "done" ||
        (evt.status &&
          evt.event === "status" &&
          [
            "completed",
            "failed",
            "awaiting_review",
            "awaiting_coach_review",
          ].includes(evt.status))
      ) {
        getSession(sessionId)
          .then((data) => {
            const s = data as unknown as SessionData;
            // Apply same monotonic guard — don't let refetch regress status
            setSession((prev) => {
              if (!prev) return s;
              const prevIdx = PIPELINE_STEPS.indexOf(prev.status);
              const fetchedIdx = PIPELINE_STEPS.indexOf(s.status);
              if (fetchedIdx < prevIdx && prevIdx !== -1 && fetchedIdx !== -1) {
                // Keep current (more advanced) status, merge other fields
                return { ...s, status: prev.status };
              }
              return s;
            });
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
          ).coach_chat_history) as
          | Array<{ role: string; text: string }>
          | undefined;
        if (Array.isArray(history) && history.length > 0) {
          setChatMessages(
            history.map((entry) => ({
              role:
                entry.role === "assistant"
                  ? "agent"
                  : (entry.role as ChatMessage["role"]),
              text: entry.text,
            })),
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
      if (
        evt.status &&
        evt.status !== "coaching" &&
        evt.status !== "awaiting_coach_review"
      ) {
        setCoachReviewOpen(false);
      }

      if (evt.event === "shortlist_review" && evt.scored_jobs) {
        const jobs = evt.scored_jobs as ScoredJobData[];
        setShortlistJobs(jobs);
        setSelectedJobIds(new Set(jobs.map((sj) => sj.job.id)));
        if (
          !shortlistApprovedRef.current &&
          (latestStatusRef.current === "tailoring" ||
            latestStatusRef.current === "awaiting_review")
        ) {
          setShortlistReviewOpen(true);
        }
      }
      if (
        evt.status &&
        evt.status !== "tailoring" &&
        evt.status !== "awaiting_review"
      ) {
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
        (evt.message?.includes("Submitting") ||
          evt.message?.includes("Skipping"))
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

      // LinkedIn update SSE events
      if (
        evt.event === "linkedin_update_progress" ||
        evt.event === "linkedin_update_complete"
      ) {
        setLinkedinProgress({
          step: String(evt.step || ""),
          section: String(evt.section || ""),
          progress: typeof evt.progress === "number" ? evt.progress : 0,
          success: evt.success as boolean | undefined,
          results: evt.results as LinkedInProgress["results"],
        });
      }
      if (evt.event === "linkedin_update_failed") {
        setLinkedinProgress({
          step: String(evt.step || "Update failed"),
          section: String(evt.section || ""),
          progress: -1,
        });
      }

      setTimeout(() => {
        const el = eventsEndRef.current;
        if (el?.parentElement) {
          el.parentElement.scrollTop = el.parentElement.scrollHeight;
        }
      }, 100);
    });
    return cleanup;
  }, [sessionId, sseKey]);

  useEffect(() => {
    const apiBase =
      process.env.NEXT_PUBLIC_API_URL ||
      (window.location.port === "3000"
        ? "http://localhost:8000"
        : window.location.origin);
    const wsUrl = apiBase.replace(/^http/, "ws") + `/ws/sessions/${sessionId}`;

    const manager = new WebSocketManager(
      wsUrl,
      (payload) => {
        const messageType = String(payload.type || "");
        if (messageType === "screenshot" || messageType === "takeover_frame") {
          if (typeof payload.image === "string") {
            setLiveBrowserImage(normalizeScreenshotSrc(String(payload.image)));
          }
          if (typeof payload.url === "string") {
            setLiveBrowserUrl(String(payload.url));
          }
          return;
        }

        if (messageType === "takeover_status") {
          setTakeoverActive(Boolean(payload.active));
          if (typeof payload.reason === "string" && payload.reason.trim()) {
            setTakeoverMessage(String(payload.reason));
          } else {
            setTakeoverMessage(null);
          }
          if (typeof payload.url === "string") {
            setLiveBrowserUrl(String(payload.url));
          }
        }
      },
      (status) => {
        setTakeoverWsStatus(status);
      },
    );

    wsManagerRef.current = manager;
    manager.connect();

    return () => {
      wsManagerRef.current?.disconnect();
      wsManagerRef.current = null;
    };
  }, [sessionId]);

  const handleSendChat = async (message: string) => {
    const msg = message.trim();
    if (!msg) return;
    const isCoachChatMode =
      coachReviewOpen || latestStatusRef.current === "awaiting_coach_review";

    setChatMessages((prev) => [...prev, { role: "user", text: msg }]);

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
              : prev,
          );
          setCoachReviewOpen(true);
        }
        if (response.message) {
          setChatMessages((prev) => [
            ...prev,
            { role: "agent", text: response.message },
          ]);
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
    }
  };

  const handleRequestTakeover = () => {
    setTakeoverMessage(null);
    wsManagerRef.current?.requestControl();
  };

  const handleReleaseTakeover = () => {
    wsManagerRef.current?.releaseControl();
    setTakeoverActive(false);
  };

  const handleTakeoverMouseAction = (payload: Record<string, unknown>) => {
    wsManagerRef.current?.sendTakeoverInput({
      input_type: "mouse",
      ...payload,
    });
  };

  const handleTakeoverKeyboardAction = (payload: Record<string, unknown>) => {
    wsManagerRef.current?.sendTakeoverInput({
      input_type: "keyboard",
      ...payload,
    });
  };

  const handleApproveShortlist = async () => {
    setShortlistSubmitting(true);
    try {
      const jobIds = Array.from(selectedJobIds);
      await submitReview(sessionId, { approved_job_ids: jobIds, feedback: "" });
      shortlistApprovedRef.current = true;
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

  const handleApproveCoachReview = async () => {
    setCoachReviewSubmitting(true);
    try {
      await submitCoachReview(sessionId, { approved: true });
      coachApprovedRef.current = true;
      setCoachReviewOpen(false);
      setSession((prev) => (prev ? { ...prev, status: "discovering" } : prev));
    } catch (e) {
      console.error("Failed to submit coach review:", e);
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

  const activePane = useMemo(() => {
    if (!session) return "overview";
    if (coachReviewOpen || session.status === "awaiting_coach_review") {
      return "coach";
    }
    if (shortlistReviewOpen || session.status === "awaiting_review") {
      return "shortlist";
    }
    if (
      interventionData ||
      submitConfirmData ||
      loginPrompt ||
      takeoverActive ||
      session.status === "applying" ||
      session.status === "needs_intervention" ||
      session.status === "paused"
    ) {
      return "apply";
    }
    if (session.status === "completed" || session.status === "failed") {
      return "summary";
    }
    return "overview";
  }, [
    coachReviewOpen,
    interventionData,
    loginPrompt,
    session,
    shortlistReviewOpen,
    submitConfirmData,
    takeoverActive,
  ]);

  const quickActions = useMemo(() => {
    if (!session) {
      return ["Explain the current step"];
    }
    if (coachReviewOpen || session.status === "awaiting_coach_review") {
      return [
        "Explain the strongest resume changes",
        "Tighten the resume for senior AI platform roles",
        "Change the coaching tone to more direct and technical",
      ];
    }
    if (shortlistReviewOpen || session.status === "awaiting_review") {
      return [
        "Explain why these jobs made the shortlist",
        "Bias harder toward remote AI platform roles",
        "Skip lower-signal frontend matches",
      ];
    }
    if (
      interventionData ||
      submitConfirmData ||
      loginPrompt ||
      session.status === "applying"
    ) {
      return [
        "Explain what the apply agent is doing now",
        "Pause after this job",
        "Skip the next job",
      ];
    }
    if (session.status === "completed") {
      return [
        "Summarize the strongest outcomes from this run",
        "List the most promising companies",
      ];
    }
    return [
      "Explain the current step",
      "Pause after the current phase",
      "Bias more toward AI agent roles",
    ];
  }, [
    coachReviewOpen,
    interventionData,
    loginPrompt,
    session,
    shortlistReviewOpen,
    submitConfirmData,
  ]);

  const chatModeLabel =
    coachReviewOpen || latestStatusRef.current === "awaiting_coach_review"
      ? "Coach"
      : activePane === "apply"
        ? "Apply"
        : "Workflow";

  const rawStepIndex = session
    ? getStepIndexForStatus(session.status, session)
    : 0;
  const currentStepIndex = Math.max(0, rawStepIndex);
  const isActive =
    session && session.status !== "completed" && session.status !== "failed";

  if (!session) {
    return (
      <div className="min-h-screen bg-background">
        <nav className="sticky top-0 z-50 border-b border-border/70 bg-background/95 px-6 py-3 shadow-sm supports-[backdrop-filter]:bg-background/90 supports-[backdrop-filter]:backdrop-blur-md">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <div className="h-6 w-40 bg-muted rounded-lg animate-pulse" />
            <div className="flex gap-3">
              <div className="h-8 w-24 bg-muted rounded-full animate-pulse" />
              <div className="h-8 w-24 bg-muted rounded-lg animate-pulse" />
            </div>
          </div>
        </nav>
        <div className="max-w-7xl mx-auto px-6 py-8">
          {/* Pipeline skeleton */}
          <div className="flex items-center gap-1 mb-8 px-4">
            {[1, 2, 3, 4, 5, 6, 7].map((i) => (
              <div key={i} className="flex items-center flex-1">
                <div className="w-8 h-8 rounded-full bg-muted animate-pulse" />
                {i < 7 && <div className="flex-1 h-0.5 mx-1 bg-muted" />}
              </div>
            ))}
          </div>
          <div className="flex gap-6">
            <div className="flex-1 space-y-4">
              <div className="h-10 w-72 bg-muted rounded-xl animate-pulse" />
              <div className="rounded-xl border border-border/50 p-6 space-y-3">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div
                    key={i}
                    className="flex gap-3 items-center animate-fade-in-up"
                    style={{ animationDelay: `${i * 100}ms` }}
                  >
                    <div className="h-4 w-16 bg-muted rounded animate-pulse" />
                    <div className="h-6 w-20 bg-muted rounded-full animate-pulse" />
                    <div className="h-4 flex-1 bg-muted/50 rounded animate-pulse" />
                  </div>
                ))}
              </div>
            </div>
            <div className="w-80 space-y-4">
              <div className="rounded-xl border border-border/50 p-5 space-y-4">
                <div className="h-5 w-24 bg-muted rounded animate-pulse" />
                {[1, 2, 3].map((i) => (
                  <div key={i}>
                    <div className="h-3 w-16 bg-muted/50 rounded animate-pulse mb-1.5" />
                    <div className="h-4 w-40 bg-muted rounded animate-pulse" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Navbar */}
      <nav className="sticky top-0 z-50 border-b border-border/70 bg-background/95 px-6 py-3 shadow-sm supports-[backdrop-filter]:bg-background/90 supports-[backdrop-filter]:backdrop-blur-md">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <Link
            href="/"
            className="text-lg font-bold bg-gradient-to-r from-blue-600 to-blue-700 bg-clip-text text-transparent"
          >
            JobHunter Agent
          </Link>
          <div className="hidden sm:flex items-center gap-1">
            <Link
              href={`/session/${sessionId}`}
              className="px-3 py-1.5 text-sm font-medium rounded-md bg-primary/10 text-primary"
            >
              Activity
            </Link>
            <Link
              href={`/session/${sessionId}/manual-apply`}
              className="px-3 py-1.5 text-sm font-medium rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
            >
              Manual Apply
            </Link>
            <Link
              href={`/session/${sessionId}/settings`}
              className="px-3 py-1.5 text-sm font-medium rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
            >
              Settings
            </Link>
          </div>
          <div className="flex items-center gap-3">
            <Badge
              variant={session.status === "completed" ? "default" : "secondary"}
              className={
                isActive
                  ? "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800 animate-pulse"
                  : session.status === "completed"
                    ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300"
                    : ""
              }
            >
              {isActive && (
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500 mr-1.5 animate-pulse" />
              )}
              {STATUS_LABELS[session.status] || session.status}
            </Badge>
            <Link href="/dashboard">
              <Button variant="outline" size="sm">
                Dashboard
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Pipeline Stepper */}
      <div className="border-b border-border/70 bg-card/95 shadow-sm supports-[backdrop-filter]:bg-card/90 supports-[backdrop-filter]:backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-6 py-4">
          <div className="flex items-center gap-0.5">
            {PIPELINE_STEPS.map((step, i) => {
              const isCompleted = i < currentStepIndex;
              const isCurrent = i === currentStepIndex;
              const isFailed = session.status === "failed" && isCurrent;
              const isBlocked =
                (session.status === "awaiting_coach_review" &&
                  step === "awaiting_coach_review") ||
                (session.status === "awaiting_review" &&
                  step === "awaiting_review") ||
                ((session.status === "needs_intervention" ||
                  session.status === "paused" ||
                  interventionData ||
                  submitConfirmData ||
                  loginPrompt) &&
                  step === "applying");
              return (
                <div
                  key={step}
                  className="flex items-center flex-1 last:flex-none"
                >
                  {/* Step pill */}
                  <div
                    className={`
                      relative flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-medium transition-all duration-500 whitespace-nowrap overflow-hidden
                      ${
                        isCompleted
                          ? "bg-blue-50 text-blue-700 dark:bg-blue-900/60 dark:text-blue-300"
                          : isFailed
                            ? "bg-red-500 text-white shadow-lg shadow-red-500/30"
                            : isBlocked
                              ? "bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200"
                              : isCurrent
                                ? "bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/30"
                                : "text-muted-foreground/60"
                      }
                    `}
                  >
                    {/* Shimmer effect on active step */}
                    {isCurrent && isActive && !isBlocked && !isFailed && (
                      <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-[gradient-shift_2s_ease_infinite] bg-[length:200%_100%]" />
                    )}
                    {isCompleted ? (
                      <svg
                        className="w-3.5 h-3.5 shrink-0"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={3}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    ) : isFailed ? (
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-white" />
                    ) : isBlocked ? (
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-current" />
                    ) : isCurrent && isActive ? (
                      <span className="relative flex h-2 w-2 shrink-0">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75" />
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-white" />
                      </span>
                    ) : (
                      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-30 shrink-0" />
                    )}
                    <span className="relative z-10">{STEP_LABELS[step]}</span>
                  </div>
                  {/* Connector */}
                  {i < PIPELINE_STEPS.length - 1 && (
                    <div className="flex-1 mx-0.5">
                      <div className="h-0.5 w-full rounded-full bg-border/50 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-700 ease-out ${
                            isFailed
                              ? "bg-red-400 dark:bg-red-500"
                              : isBlocked
                                ? "bg-amber-400 dark:bg-amber-500"
                                : isCurrent && isActive
                                  ? "bg-gradient-to-r from-blue-500 to-blue-600 animate-progress-pulse"
                                  : "bg-blue-400 dark:bg-blue-500"
                          }`}
                          style={{
                            width: isCompleted
                              ? "100%"
                              : isCurrent
                                ? `${Math.max(stepProgress, 5)}%`
                                : "0%",
                          }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Intervention Banner */}
      {interventionData && (
        <div className="bg-amber-50 dark:bg-amber-950/50 border-b border-amber-200 dark:border-amber-800 px-6 py-4">
          <div className="max-w-7xl mx-auto flex items-start gap-4">
            <div className="shrink-0 mt-0.5">
              <svg
                className="w-6 h-6 text-amber-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
                />
              </svg>
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-amber-800 dark:text-amber-200">
                Agent Paused — Needs Your Help
              </h3>
              <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                <span className="font-medium">
                  {interventionData.job_title}
                </span>{" "}
                at {interventionData.company}
              </p>
              <p className="text-sm text-amber-600 dark:text-amber-400 mt-1">
                {interventionData.reason}
              </p>
              <p className="text-xs text-amber-500 mt-2">
                Use Browser Takeover below to interact with the live page, or
                fix it directly on the desktop browser, then click Resume.
              </p>
            </div>
            <Button
              onClick={handleResumeIntervention}
              className="shrink-0 bg-amber-600 hover:bg-amber-700 text-white"
            >
              Resume Agent
            </Button>
          </div>
        </div>
      )}

      {/* Submit Confirmation Banner */}
      {submitConfirmData && (
        <div className="bg-blue-50 dark:bg-blue-950/50 border-b border-blue-200 dark:border-blue-800 px-6 py-4">
          <div className="max-w-7xl mx-auto flex items-start gap-4">
            <div className="shrink-0 mt-0.5">
              <svg
                className="w-6 h-6 text-blue-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-blue-800 dark:text-blue-200">
                Ready to Submit — Review & Approve
              </h3>
              <p className="text-sm text-blue-700 dark:text-blue-300 mt-1">
                <span className="font-medium">
                  {submitConfirmData.job_title}
                </span>{" "}
                at {submitConfirmData.company}
              </p>
              <p className="text-sm text-blue-600 dark:text-blue-400 mt-1">
                {submitConfirmData.fields_filled} fields filled. Review the form
                in the browser window before submitting.
              </p>
              <p className="text-xs text-blue-500 mt-2">
                Review the live page below in Browser Takeover, then submit or
                skip this application.
              </p>
            </div>
            <div className="flex gap-2 shrink-0">
              <Button
                variant="outline"
                onClick={() => handleSubmitDecision("skip")}
                className="border-blue-300 text-blue-700 hover:bg-blue-100 dark:border-blue-700 dark:text-blue-300"
              >
                Skip
              </Button>
              <Button
                onClick={() => handleSubmitDecision("submit")}
                className="bg-blue-600 hover:bg-blue-700 text-white"
              >
                Submit Application
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Main content */}
      <div className="mx-auto grid max-w-7xl flex-1 w-full gap-5 px-5 py-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-5">
          <Card className="overflow-hidden">
            <CardHeader className="border-b border-border/50 pb-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <CardTitle className="text-sm font-semibold">
                    Browser Takeover
                  </CardTitle>
                  <p className="mt-1 text-xs text-muted-foreground">
                    The live page appears here during application work. Use this
                    when login, CAPTCHA, or ambiguous forms need direct control.
                  </p>
                </div>
                <Badge variant={takeoverActive ? "default" : "secondary"}>
                  {takeoverActive ? "Live control active" : "On standby"}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <TakeoverViewer
                imageUrl={liveBrowserImage}
                currentUrl={liveBrowserUrl}
                wsStatus={takeoverWsStatus}
                controlActive={takeoverActive}
                onRequestControl={handleRequestTakeover}
                onReleaseControl={handleReleaseTakeover}
                onMouseAction={handleTakeoverMouseAction}
                onKeyboardAction={handleTakeoverKeyboardAction}
              />
              {takeoverMessage && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  {takeoverMessage}
                </p>
              )}
            </CardContent>
          </Card>

          <Card className="flex min-h-[420px] flex-col overflow-hidden">
            <CardHeader className="border-b border-border/50 pb-2">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                    Live Status
                  </CardTitle>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Surfacing the latest meaningful events instead of every
                    duplicate status tick.
                  </p>
                </div>
                <span className="text-xs text-muted-foreground">
                  {surfacedEvents.length} surfaced / {events.length} raw
                </span>
              </div>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 overflow-y-auto py-3 space-y-1">
              {surfacedEvents.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <svg
                    className="mb-3 h-10 w-10 animate-pulse opacity-50"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={1.5}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"
                    />
                  </svg>
                  <p className="text-sm font-medium">Waiting for events...</p>
                  <p className="mt-1 text-xs">The agent is warming up</p>
                </div>
              )}
              {surfacedEvents.map((evt, i) => {
                const time = evt.timestamp
                  ? new Date(evt.timestamp).toLocaleTimeString()
                  : "";

                if (evt.event?.endsWith("_progress")) {
                  const label = evt.event.replace("_progress", "");
                  const pct =
                    typeof evt.progress === "number" ? evt.progress : undefined;
                  return (
                    <div
                      key={`${evt.event}-${i}`}
                      className="flex items-center gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-muted/50 animate-fade-in-up"
                    >
                      <span className="w-20 shrink-0 whitespace-nowrap text-[11px] font-mono text-muted-foreground">
                        {time}
                      </span>
                      <span
                        className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                          AGENT_COLORS[label] || AGENT_COLORS.system
                        }`}
                      >
                        {AGENT_DISPLAY_NAMES[label] || label}
                      </span>
                      <span
                        className={`min-w-0 flex-1 break-words text-sm ${
                          typeof evt.step === "string" &&
                          evt.step.startsWith("Skipped")
                            ? "text-amber-600 dark:text-amber-400"
                            : "text-foreground/80"
                        }`}
                      >
                        {evt.step}
                      </span>
                      {pct !== undefined && pct >= 0 && (
                        <span className="ml-auto text-[11px] font-mono tabular-nums text-muted-foreground">
                          {Math.round(pct)}%
                        </span>
                      )}
                    </div>
                  );
                }

                const agent = evt.agent || evt.event || "system";
                const msg =
                  evt.message ||
                  (evt.event === "discovery"
                    ? `Found ${evt.jobs_found ?? 0} matching ${
                        (evt.jobs_found ?? 0) === 1 ? "job" : "jobs"
                      }`
                    : "") ||
                  (evt.event === "scoring"
                    ? `Ranked ${evt.scored_count ?? 0} jobs by fit`
                    : "") ||
                  (evt.event === "agent_complete"
                    ? `${agent.replace(/_/g, " ")} finished`
                    : "") ||
                  evt.status ||
                  evt.event;

                return (
                  <div
                    key={`${evt.event}-${i}`}
                    className="flex items-center gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-muted/50 animate-fade-in-up"
                  >
                    <span className="w-20 shrink-0 whitespace-nowrap text-[11px] font-mono text-muted-foreground">
                      {time}
                    </span>
                    <span
                      className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                        AGENT_COLORS[agent] || AGENT_COLORS.system
                      }`}
                    >
                      {AGENT_DISPLAY_NAMES[agent] || agent}
                    </span>
                    <span
                      className={`min-w-0 flex-1 break-words text-sm ${
                        evt.event === "error"
                          ? "font-medium text-red-500"
                          : "text-foreground/80"
                      }`}
                    >
                      {msg}
                    </span>
                  </div>
                );
              })}
              <div ref={eventsEndRef} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4 overflow-y-auto border-l border-border/50 bg-card/30 px-5 pb-5 pt-0">
          <Card className="border-blue-100 bg-gradient-to-br from-blue-50 to-sky-50 dark:border-blue-900 dark:from-blue-950/50 dark:to-sky-950/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <svg
                  className="w-4 h-4 text-blue-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                Session
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2.5 text-sm">
              {isActive && (
                <div className="mb-2 flex items-center justify-between border-b border-border/30 pb-2">
                  <span className="text-xs uppercase tracking-wider text-muted-foreground">
                    Elapsed
                  </span>
                  <span className="font-mono text-lg font-bold text-blue-600 dark:text-blue-400">
                    {elapsedMin}:{elapsedSec.toString().padStart(2, "0")}
                  </span>
                </div>
              )}
              <div>
                <span className="text-xs uppercase tracking-wider text-muted-foreground">
                  Keywords
                </span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {session.keywords?.map((kw, i) => (
                    <Badge
                      key={i}
                      variant="secondary"
                      className="bg-white/80 text-xs dark:bg-white/10"
                    >
                      {kw}
                    </Badge>
                  ))}
                </div>
              </div>
              <div className="grid w-full grid-cols-2 gap-2 pt-1">
                {[
                  {
                    value: session.applications_used ?? 0,
                    label: "Applied",
                    color: "text-blue-600 dark:text-blue-400",
                  },
                  {
                    value: session.applications_submitted?.length ?? 0,
                    label: "Submitted",
                    color: "text-emerald-600 dark:text-emerald-400",
                  },
                  {
                    value: session.applications_failed?.length ?? 0,
                    label: "Failed",
                    color: "text-red-500",
                  },
                  {
                    value: Array.isArray(session.applications_skipped)
                      ? session.applications_skipped.length
                      : (session.applications_skipped ?? 0),
                    label: "Skipped",
                    color: "text-amber-600 dark:text-amber-400",
                  },
                ].map(({ value, label, color }) => (
                  <a
                    key={label}
                    href={`/session/${sessionId}/manual-apply`}
                    className="cursor-pointer rounded-lg bg-white/60 py-2.5 text-center transition-colors hover:bg-white/90 dark:bg-white/5 dark:hover:bg-white/10"
                  >
                    <p className={`text-xl font-bold ${color}`}>{value}</p>
                    <p className="text-xs text-muted-foreground">{label}</p>
                  </a>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="overflow-hidden">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between gap-2">
                <CardTitle className="text-sm font-semibold">
                  Session Steering
                </CardTitle>
                <Badge variant="outline">Controlling {chatModeLabel}</Badge>
              </div>
              <p className="text-xs text-muted-foreground">
                Suggested commands are based on the current workflow phase.
              </p>
            </CardHeader>
            <CardContent className="space-y-3 p-0">
              <div className="flex flex-wrap gap-2 px-4 pt-1">
                {quickActions.map((action) => (
                  <Button
                    key={action}
                    variant="outline"
                    size="sm"
                    className="h-auto whitespace-normal text-left text-xs"
                    onClick={() => sendSuggestedMessage(action)}
                    disabled={!isActive}
                  >
                    {action}
                  </Button>
                ))}
              </div>
              <div className="h-72">
                <ChatPanel
                  messages={chatMessages}
                  onSend={handleSendChat}
                  disabled={!isActive}
                  placeholder={
                    coachReviewOpen ||
                    latestStatusRef.current === "awaiting_coach_review"
                      ? "Ask the coach to revise your resume or strategy..."
                      : "Ask the agent to adjust..."
                  }
                />
              </div>
            </CardContent>
          </Card>

          {session.coach_output && activePane !== "summary" && (
            <Card className="border-slate-200 bg-gradient-to-br from-slate-50 to-gray-50 dark:border-slate-800 dark:from-slate-950/50 dark:to-gray-950/50">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <svg
                    className="w-4 h-4 text-slate-500"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
                    />
                  </svg>
                  Career Coach
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    Resume Score
                  </span>
                  <CircularProgress
                    value={session.coach_output.resume_score.overall}
                    size={42}
                    strokeWidth={4}
                    showValue
                  />
                </div>
                <TooltipProvider delayDuration={300}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <p className="cursor-help line-clamp-3 text-xs italic leading-relaxed text-muted-foreground">
                        {session.coach_output.confidence_message}
                      </p>
                    </TooltipTrigger>
                    <TooltipContent
                      side="left"
                      className="max-w-sm text-xs leading-relaxed"
                    >
                      {session.coach_output.confidence_message}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </CardContent>
            </Card>
          )}

          {session.coach_output?.linkedin_advice &&
            session.coach_output.linkedin_advice.length > 0 &&
            activePane !== "summary" && (
              <LinkedInUpdateButton
                sessionId={sessionId}
                linkedinAdvice={session.coach_output.linkedin_advice}
                linkedinUrl={session.linkedin_url}
                linkedinProgress={linkedinProgress}
                disabled
              />
            )}

          {shortlistJobs.length > 0 && activePane !== "summary" && (
            <Card className="border-amber-100 bg-gradient-to-br from-amber-50 to-orange-50 dark:border-amber-900 dark:from-amber-950/50 dark:to-orange-950/50">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <svg
                    className="w-4 h-4 text-amber-500"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                    />
                  </svg>
                  Shortlist
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">
                    Jobs scored
                  </span>
                  <span className="font-semibold">{shortlistJobs.length}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">
                    Top score
                  </span>
                  <CircularProgress
                    value={shortlistJobs[0]?.score || 0}
                    size={28}
                    strokeWidth={3}
                    showValue
                  />
                </div>
                {session.status === "awaiting_review" && (
                  <Button
                    size="sm"
                    className="mt-1 w-full"
                    onClick={() => setShortlistReviewOpen(true)}
                  >
                    Review Shortlist
                  </Button>
                )}
              </CardContent>
            </Card>
          )}

          {sessionSummary && session.status === "completed" && (
            <Card className="border-emerald-200 bg-gradient-to-br from-emerald-50 to-teal-50 dark:border-emerald-800 dark:from-emerald-950/50 dark:to-teal-950/50">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold text-emerald-700 dark:text-emerald-300 flex items-center gap-2">
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                  Session Complete
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="grid grid-cols-2 gap-2">
                  {[
                    {
                      label: "Discovered",
                      value: sessionSummary.total_discovered,
                      color: "",
                    },
                    {
                      label: "Scored",
                      value: sessionSummary.total_scored,
                      color: "",
                    },
                    {
                      label: "Applied",
                      value: sessionSummary.total_applied,
                      color: "text-emerald-600 dark:text-emerald-400",
                    },
                    {
                      label: "Failed",
                      value: sessionSummary.total_failed,
                      color: "text-red-500",
                    },
                    {
                      label: "Skipped",
                      value: sessionSummary.total_skipped,
                      color: "",
                    },
                    {
                      label: "Avg Fit",
                      value: `${sessionSummary.avg_fit_score}/100`,
                      color: "",
                    },
                  ].map(({ label, value, color }) => (
                    <div
                      key={label}
                      className="flex items-center justify-between py-1"
                    >
                      <span className="text-xs text-muted-foreground">
                        {label}
                      </span>
                      <span className={`font-semibold ${color}`}>{value}</span>
                    </div>
                  ))}
                </div>
                <div className="flex items-center justify-between border-t border-emerald-200/50 py-1 dark:border-emerald-800/50">
                  <span className="text-xs text-muted-foreground">
                    Duration
                  </span>
                  <span className="font-semibold">
                    {sessionSummary.duration_minutes}m
                  </span>
                </div>
                {sessionSummary.top_companies.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-xs text-muted-foreground">
                      Top Companies
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {sessionSummary.top_companies
                        .slice(0, 5)
                        .map((company, i) => (
                          <Badge
                            key={i}
                            variant="secondary"
                            className="bg-white/80 text-xs dark:bg-white/10"
                          >
                            {company}
                          </Badge>
                        ))}
                    </div>
                  </div>
                )}
                {sessionSummary.next_steps.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-xs text-muted-foreground">
                      Next Steps
                    </p>
                    <ul className="space-y-1.5">
                      {sessionSummary.next_steps.map((step, i) => (
                        <li
                          key={i}
                          className="flex items-start gap-1.5 text-xs text-foreground/70"
                        >
                          <span className="mt-0.5 shrink-0 text-emerald-500">
                            {i + 1}.
                          </span>
                          {step}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {(session.status === "completed" || session.status === "failed") && (
            <Card className="border-amber-200 dark:border-amber-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold flex items-center gap-2 text-amber-700 dark:text-amber-300">
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M12.066 11.2a1 1 0 000 1.6l5.334 4A1 1 0 0019 16V8a1 1 0 00-1.6-.8l-5.333 4zM4.066 11.2a1 1 0 000 1.6l5.334 4A1 1 0 0011 16V8a1 1 0 00-1.6-.8l-5.334 4z"
                    />
                  </svg>
                  Checkpoints
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {checkpoints.length === 0 ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full text-xs"
                    onClick={handleLoadCheckpoints}
                  >
                    Load Checkpoints
                  </Button>
                ) : (
                  <div className="space-y-2">
                    <p className="text-xs text-muted-foreground">
                      Resume from a meaningful checkpoint instead of restarting
                      the whole run.
                    </p>
                    {checkpoints
                      .filter((cp) =>
                        [
                          "paused",
                          "awaiting_review",
                          "awaiting_coach_review",
                        ].includes(cp.status),
                      )
                      .map((cp) => (
                        <button
                          key={cp.checkpoint_id}
                          className="flex w-full items-center justify-between rounded-xl border border-amber-200 px-3 py-3 text-left text-xs transition-colors hover:bg-amber-50 disabled:opacity-60 dark:border-amber-900 dark:hover:bg-amber-950/40"
                          disabled={rewindLoading}
                          onClick={() => handleRewind(cp.checkpoint_id)}
                          type="button"
                        >
                          <div>
                            <p className="font-medium text-foreground">
                              {checkpointLabel(cp.status)}
                            </p>
                            <p className="mt-1 text-muted-foreground">
                              {cp.application_queue} jobs queued
                            </p>
                          </div>
                          <span className="text-amber-600">Rewind</span>
                        </button>
                      ))}
                    {checkpoints.filter((cp) =>
                      [
                        "paused",
                        "awaiting_review",
                        "awaiting_coach_review",
                      ].includes(cp.status),
                    ).length === 0 && (
                      <p className="text-xs text-muted-foreground">
                        No rewindable checkpoints found.
                      </p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {session.applications_submitted &&
            session.applications_submitted.length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <svg
                      className="w-4 h-4 text-emerald-500"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    Applications
                  </CardTitle>
                </CardHeader>
                <CardContent className="max-h-64 space-y-1 overflow-y-auto">
                  {session.applications_submitted.map((app, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs transition-colors hover:bg-muted/50"
                    >
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-950">
                        <svg
                          className="h-3 w-3 text-emerald-600 dark:text-emerald-400"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth={3}
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      </span>
                      <span className="flex-1 truncate text-foreground/70">
                        {app.job_id.slice(0, 12)}...
                      </span>
                      <Badge variant="secondary" className="text-[10px]">
                        {app.status}
                      </Badge>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
        </div>
      </div>

      {/* Coach Review Modal */}
      <Dialog open={coachReviewOpen} onOpenChange={setCoachReviewOpen}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center">
                <svg
                  className="w-4 h-4 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
                  />
                </svg>
              </span>
              Review Your Coached Resume
            </DialogTitle>
            <DialogDescription>
              The Career Coach has analyzed and rewritten your resume. Review
              the results below, then approve to continue to job discovery.
            </DialogDescription>
          </DialogHeader>
          {coachReviewData && (
            <div className="space-y-4">
              <CoachPanel
                coach={coachReviewData}
                sessionId={sessionId}
                linkedinUrl={session?.linkedin_url}
                linkedinProgress={linkedinProgress}
              />
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold">
                    Coach Chat
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0 h-56">
                  <ChatPanel
                    messages={chatMessages}
                    onSend={handleSendChat}
                    disabled={false}
                    placeholder="Ask the coach to revise your resume or strategy..."
                  />
                </CardContent>
              </Card>
            </div>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCoachReviewOpen(false)}
              disabled={coachReviewSubmitting}
            >
              Review Later
            </Button>
            <Button
              onClick={handleApproveCoachReview}
              loading={coachReviewSubmitting}
            >
              Approve & Start Job Discovery
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Shortlist Review Modal */}
      <Dialog open={shortlistReviewOpen} onOpenChange={setShortlistReviewOpen}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center">
                <svg
                  className="w-4 h-4 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                  />
                </svg>
              </span>
              Review Job Shortlist
            </DialogTitle>
            <DialogDescription>
              Select the jobs you want to apply to. Deselect any you want to
              skip.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 max-h-[55vh] overflow-y-auto">
            {shortlistJobs.map((sj) => {
              const selected = selectedJobIds.has(sj.job.id);
              return (
                <div
                  key={sj.job.id}
                  className={`border rounded-xl p-4 cursor-pointer transition-all duration-200 ${
                    selected
                      ? "border-blue-300 bg-blue-50/50 dark:bg-blue-950/30 dark:border-blue-700 shadow-sm"
                      : "border-border hover:border-border/80 opacity-60 hover:opacity-80"
                  }`}
                  onClick={() => toggleJobSelection(sj.job.id)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="font-medium text-sm">{sj.job.title}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {sj.job.company} — {sj.job.location}
                      </p>
                      {sj.reasons && sj.reasons.length > 0 && (
                        <ul className="mt-2 space-y-0.5">
                          {sj.reasons.map((r, ri) => (
                            <li
                              key={ri}
                              className="text-xs text-muted-foreground flex items-start gap-1.5"
                            >
                              <span className="text-blue-400 mt-0.5">-</span>{" "}
                              {r}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                    <div className="flex items-center gap-3 ml-4">
                      <CircularProgress
                        value={sj.score}
                        size={40}
                        strokeWidth={3.5}
                        showValue
                      />
                      <Badge variant="secondary" className="text-xs">
                        {sj.job.board}
                      </Badge>
                      <div
                        className={`w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all ${
                          selected
                            ? "border-blue-500 bg-blue-500 text-white shadow-sm shadow-blue-500/30"
                            : "border-muted-foreground/30"
                        }`}
                      >
                        {selected && (
                          <svg
                            className="w-3 h-3"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={3}
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M5 13l4 4L19 7"
                            />
                          </svg>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <DialogFooter className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {selectedJobIds.size} of {shortlistJobs.length} jobs selected
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => setShortlistReviewOpen(false)}
                disabled={shortlistSubmitting}
              >
                Review Later
              </Button>
              <Button
                onClick={handleApproveShortlist}
                loading={shortlistSubmitting}
                disabled={selectedJobIds.size === 0}
              >
                Apply to {selectedJobIds.size} Jobs
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Pre-login modal */}
      <Dialog open={!!loginPrompt} onOpenChange={() => {}}>
        <DialogContent
          className="sm:max-w-md"
          onInteractOutside={(e) => e.preventDefault()}
        >
          <DialogHeader>
            <DialogTitle>
              Log in to{" "}
              {loginPrompt?.board?.replace(/^\w/, (c) => c.toUpperCase())}
            </DialogTitle>
            <DialogDescription>{loginPrompt?.message}</DialogDescription>
          </DialogHeader>
          <div className="bg-muted/50 rounded p-3 text-sm text-muted-foreground">
            A browser window has opened with the login page. Log in with your
            account, then click the button below to continue.
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
              I&apos;ve Logged In — Continue
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
