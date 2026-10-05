// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { type ChatMessage } from "@/components/ChatPanel";
import { type RunOverrides } from "@/components/run/AdjustDialog";
import type { Checkpoint, CoachOutput } from "@/lib/api";
import {
  confirmLogin,
  connectSSE,
  getApplicationRules,
  getSession,
  killSession,
  listCheckpoints,
  rerunSession,
  resumeIntervention,
  resumeSession,
  rewindSession,
  sendCoachChat,
  sendSteer,
  submitCoachReview,
  submitDecision,
  submitReview,
  updateApplicationRules,
} from "@/lib/api";
import { addApplicationAnswer, type AnswerScope } from "@/lib/applicationAnswers";
import { liveViewEnds, liveViewFromEvent, type LiveViewState } from "@/lib/liveView";
import {
  shouldRefreshSession,
  TERMINAL
} from "@/lib/run";
import { resolveRunStatus, restoreShortlistSelection } from "@/lib/run-status";
import { applySessionEvent } from "./session-events";

import type { ScoredJobData, SessionData, SessionSummaryData, SSEEvent } from "./types";

export function useSessionRun(sessionId: string) {
  // Send Gmail token to backend via server-side proxy (tokens never touch the browser)
  const gmailTokenSent = useRef(false);
  useEffect(() => {
    if(gmailTokenSent.current) return;
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
    getApplicationRules().then((rules) => { if(active) setSavedAnswerRules(rules); }).catch(() => { });
    return () => { active = false; };
  }, []);
  async function saveAnswer(question: AnswerScope, answer: string) {
    // Serialize cards' saves and reload current rules so separate answers never
    // overwrite one another from a stale page snapshot.
    const operation = answerSaveQueue.current.catch(() => { }).then(async () => {
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
      if(cachedEvents) setEvents(JSON.parse(cachedEvents) as SSEEvent[]);
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
      if(selectedJobIds.has(sj.job.id)) {
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
  const manuallyReviewedEligibilityRef = useRef<Set<string>>(new Set());
  function restoreShortlist(jobs: ScoredJobData[]) {
    setShortlistJobs(jobs);
    const initialized = shortlistSelectionInitializedRef.current;
    shortlistSelectionInitializedRef.current = true;
    setSelectedJobIds((current) => restoreShortlistSelection(
      current,
      jobs.filter((sj) => sj.eligibility_status !== "not_met").map((sj) => sj.job.id),
      initialized,
      jobs.filter((sj) => sj.eligibility_status === "met").map((sj) => sj.job.id),
      manuallyReviewedEligibilityRef.current
    ));
  }

  // Persist events & session to sessionStorage so navigation doesn't lose progress
  useEffect(() => {
    try {
      if(cacheLoaded) sessionStorage.setItem(eventsStorageKey, JSON.stringify(events));
    } catch {
      /* quota exceeded – non-critical */
    }
  }, [events, eventsStorageKey, cacheLoaded]);

  useEffect(() => {
    if(!session) return;
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
    if(!sessionStartTime) return;
    if(session?.status === "completed" || session?.status === "failed") return;
    setElapsedSeconds(Math.floor((Date.now() - sessionStartTime) / 1000));
    const interval = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - sessionStartTime) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [sessionStartTime, session?.status]);
  useEffect(() => {
    const requestedAtApproval = approvalVersionRef.current;
    getSession(sessionId)
      .then((data) => {
        if(requestedAtApproval !== approvalVersionRef.current) return;
        const snapshot = data as unknown as SessionData;
        const s = {
          ...snapshot, status: resolveRunStatus(latestStatusRef.current, snapshot.status, "snapshot", {
            coach: coachApprovedRef.current, shortlist: shortlistApprovedRef.current, settling: settlingReviewRef.current,
          })
        };
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
        if(pastCoach.includes(s.status)) coachApprovedRef.current = true;
        if(pastShortlist.includes(s.status)) shortlistApprovedRef.current = true;

        // Restore modals from persisted state on page reload
        if(s.status === "awaiting_coach_review" && s.coach_output) {
          setCoachReviewData(s.coach_output as unknown as CoachOutput);
          setCoachReviewOpen(true);
          if(Array.isArray(s.coach_chat_history) && s.coach_chat_history.length > 0) {
            setChatMessages(
              s.coach_chat_history.map((entry) => ({
                role: entry.role === "assistant" ? "agent" : (entry.role as ChatMessage["role"]),
                text: entry.text,
              }))
            );
          }
        }
        if(s.status === "awaiting_review" && s.scored_jobs && s.scored_jobs.length > 0) {
          const jobs = s.scored_jobs as ScoredJobData[];
          restoreShortlist(jobs);
          setShortlistReviewOpen(true);
        }
        if(s.status === "completed" && s.session_summary) {
          setSessionSummary(s.session_summary as unknown as SessionSummaryData);
        }
      })
      .catch(() => {
        if(requestedAtApproval !== approvalVersionRef.current) return;
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
      if(evt.event === "ping") return;

      // Browserbase live view: embed the cloud browser instead of a screenshot feed.
      const nextLiveView = liveViewFromEvent(evt);
      if(nextLiveView) setLiveView(nextLiveView);
      if(liveViewEnds(evt)) setLiveView(null);

      setEvents((prev) => {
        const last = prev[prev.length - 1];
        if(last && last.event === evt.event) {
          const lastKey = last.message || last.step || last.status || "";
          const evtKey = evt.message || evt.step || evt.status || "";
          if(lastKey && lastKey === evtKey) return prev;
        }
        return [...prev, evt];
      });

      if(
        evt.status &&
        (evt.event === "status" ||
          evt.event === "done" ||
          evt.event === "coach_review" ||
          evt.event === "shortlist_review")
      ) {
        latestStatusRef.current = resolveRunStatus(latestStatusRef.current, evt.status, "stream", { coach: coachApprovedRef.current, shortlist: shortlistApprovedRef.current, settling: settlingReviewRef.current });
      }

      // Show browser notification for verification code requests
      if(evt.event === "verification_required") {
        if(typeof window !== "undefined" && "Notification" in window) {
          Notification.requestPermission().then((perm) => {
            if(perm === "granted") {
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
      setSession((prev) => applySessionEvent(prev, evt, {
        coach: coachApprovedRef.current, shortlist: shortlistApprovedRef.current, settling: settlingReviewRef.current,
      }));

      // Sparse result events do not contain cumulative counts. Replace totals
      // from durable state, so repeated/replayed events cannot double-count.
      // Routine progress events already carry totals and need no extra request.
      if(
        shouldRefreshSession(evt)
      ) {
        const requestedAtApproval = approvalVersionRef.current;
        getSession(sessionId)
          .then((data) => {
            if(requestedAtApproval !== approvalVersionRef.current) return;
            const s = data as unknown as SessionData;
            const nextStatus = resolveRunStatus(latestStatusRef.current, s.status, "snapshot", {
              coach: coachApprovedRef.current, shortlist: shortlistApprovedRef.current, settling: settlingReviewRef.current,
            });
            latestStatusRef.current = nextStatus;
            // Once durable state has advanced, a later interrupt can be a new gate.
            if(s.status === nextStatus && s.status !== "awaiting_coach_review" && s.status !== "awaiting_review") settlingReviewRef.current = null;
            if(nextStatus === "awaiting_coach_review") {
              coachApprovedRef.current = false;
              if(s.coach_output) {
                setCoachReviewData(s.coach_output as unknown as CoachOutput);
                setCoachReviewOpen(true);
              }
            }
            if(nextStatus === "awaiting_review") {
              shortlistApprovedRef.current = false;
              if(s.scored_jobs?.length) {
                const jobs = s.scored_jobs as ScoredJobData[];
                restoreShortlist(jobs);
                setShortlistReviewOpen(true);
              }
            }
            setSession((prev) => ({
              ...s, status: prev ? resolveRunStatus(prev.status, nextStatus, "snapshot", {
                coach: coachApprovedRef.current, shortlist: shortlistApprovedRef.current, settling: settlingReviewRef.current,
              }) : nextStatus
            }));
          })
          .catch(() => { });
      }

      if(evt.event === "coach_review" && evt.coach_output) {
        setCoachReviewData(evt.coach_output as unknown as CoachOutput);
        const history = (evt.data?.coach_chat_history ||
          (
            evt as unknown as {
              coach_chat_history?: Array<{ role: string; text: string }>;
            }
          ).coach_chat_history) as Array<{ role: string; text: string }> | undefined;
        if(Array.isArray(history) && history.length > 0) {
          setChatMessages(
            history.map((entry) => ({
              role: entry.role === "assistant" ? "agent" : (entry.role as ChatMessage["role"]),
              text: entry.text,
            }))
          );
        }
        if(
          !coachApprovedRef.current &&
          (latestStatusRef.current === "coaching" ||
            latestStatusRef.current === "awaiting_coach_review")
        ) {
          setCoachReviewOpen(true);
        }
      }
      if(evt.status && latestStatusRef.current !== "coaching" && latestStatusRef.current !== "awaiting_coach_review") {
        setCoachReviewOpen(false);
      }

      if(evt.event === "shortlist_review" && evt.scored_jobs && latestStatusRef.current === "awaiting_review" && !shortlistApprovedRef.current) {
        const jobs = evt.scored_jobs as ScoredJobData[];
        restoreShortlist(jobs);
        setShortlistReviewOpen(true);
      }
      if(evt.status && latestStatusRef.current !== "tailoring" && latestStatusRef.current !== "awaiting_review") {
        setShortlistReviewOpen(false);
      }

      if(evt.event === "done" && evt.session_summary) {
        setSessionSummary(evt.session_summary);
      }

      if(evt.event === "status" && evt.status === "steering" && evt.message) {
        setChatMessages((prev) => {
          const nextText = String(evt.message || "Steering updated.");
          const last = prev[prev.length - 1];
          if(last?.role === "agent" && last.text === nextText) {
            return prev;
          }
          return [...prev, { role: "agent", text: nextText }];
        });
      }
      if(evt.event === "error" && evt.message) {
        setChatMessages((prev) => [
          ...prev,
          { role: "system", text: evt.message || "An error occurred." },
        ]);
      }

      // Handle agent intervention request
      if(evt.event === "needs_intervention") {
        const d = (evt.data || evt) as Record<string, unknown>;
        if(d.reason) {
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
      if(evt.event === "ready_to_submit") {
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
      if(evt.status === "applying" && evt.message?.includes("resuming")) {
        setInterventionData(null);
      }
      if(
        evt.status === "applying" &&
        (evt.message?.includes("Submitting") || evt.message?.includes("Skipping"))
      ) {
        setSubmitConfirmData(null);
      }

      // Pre-login flow: show login modal when apply agent needs authentication
      if(evt.event === "login_required") {
        const d = (evt.data || evt) as Record<string, unknown>;
        setLoginPrompt({
          board: String(d.board || "unknown"),
          message: String(d.message || "Please log in in the browser window."),
        });
      }
      if(evt.event === "login_complete") {
        setLoginPrompt(null);
      }

    }, (connected) => {
      setSseConnected(connected);
      if(connected) {
        setSseFailCount(0);
      } else {
        setSseFailCount((c) => c + 1);
      }
    });
    return cleanup;
  }, [sessionId, sseKey]);

  const handleSendChat = async (message: string) => {
    const msg = message.trim();
    if(!msg) return;
    const isCoachChatMode = coachReviewOpen || latestStatusRef.current === "awaiting_coach_review";

    setChatMessages((prev) => [...prev, { role: "user", text: msg }]);
    setChatLoading(true);

    try {
      if(isCoachChatMode) {
        const response = await sendCoachChat(sessionId, { message: msg });
        if(response.coach_output) {
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
        if(response.message) {
          setChatMessages((prev) => [...prev, { role: "agent", text: response.message }]);
        }
        return;
      }

      const response = await sendSteer(sessionId, {
        message: msg,
        mode: "status",
      });
      if(response.message) {
        setChatMessages((prev) => {
          const last = prev[prev.length - 1];
          if(last?.role === "agent" && last.text === response.message) {
            return prev;
          }
          return [...prev, { role: "agent", text: response.message }];
        });
      }
    } catch(e) {
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
      const jobIds = shortlistJobs.filter((sj) => selectedJobIds.has(sj.job.id) && sj.eligibility_status !== "not_met").map((sj) => sj.job.id);
      if(!jobIds.length) throw new Error("Select a matching job or review an unresolved job before approving.");
      await submitReview(sessionId, { approved_job_ids: jobIds, feedback: "" });
      shortlistApprovedRef.current = true;
      shortlistSelectionInitializedRef.current = false;
      manuallyReviewedEligibilityRef.current.clear();
      settlingReviewRef.current = "awaiting_review";
      approvalVersionRef.current += 1;
      latestStatusRef.current = "applying";
      setShortlistReviewOpen(false);
      setShortlistSubmitting(false);
      setSession((prev) => (prev ? { ...prev, status: "applying", application_queue: jobIds } : prev));
    } catch(e) {
      toast.error(e instanceof Error ? e.message : "Could not approve the shortlist. Try again.");
      setShortlistSubmitting(false);
    }
  };

  const toggleJobSelection = (jobId: string) => {
    const job = shortlistJobs.find((sj) => sj.job.id === jobId);
    if(!job || job.eligibility_status === "not_met") return;
    const next = new Set(selectedJobIds);
    if(next.has(jobId)) {
      next.delete(jobId);
      manuallyReviewedEligibilityRef.current.delete(jobId);
    } else {
      next.add(jobId);
      if(job.eligibility_status !== "met") manuallyReviewedEligibilityRef.current.add(jobId);
    }
    setSelectedJobIds(next);
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
    } catch(e) {
      toast.error(e instanceof Error ? e.message : "Could not approve the resume. Try again.");
    } finally {
      setCoachReviewSubmitting(false);
    }
  };

  const handleResumeIntervention = async () => {
    try {
      await resumeIntervention(sessionId);
      setInterventionData(null);
    } catch(e) {
      console.error("Failed to resume:", e);
    }
  };

  const handleSubmitDecision = async (decision: "submit" | "skip") => {
    try {
      await submitDecision(sessionId, decision);
      setSubmitConfirmData(null);
    } catch(e) {
      console.error("Failed to send submit decision:", e);
    }
  };

  const handleLoadCheckpoints = async () => {
    try {
      const cps = await listCheckpoints(sessionId);
      setCheckpoints(cps);
    } catch(e) {
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
      manuallyReviewedEligibilityRef.current.clear();
      settlingReviewRef.current = null;
      approvalVersionRef.current += 1;
      latestStatusRef.current = "applying";
      // Update session status
      setSession((prev) => (prev ? { ...prev, status: "applying" } : prev));
      // Trigger SSE reconnection (old EventSource was closed on "done")
      setSseKey((k) => k + 1);
    } catch(e) {
      console.error("Failed to rewind:", e);
    } finally {
      setRewindLoading(false);
    }
  };

  const sendSuggestedMessage = (message: string) => {
    void handleSendChat(message);
  };

  const liveViewJobLabel = useMemo(() => {
    if(!liveView) return undefined;
    const match = (session?.scored_jobs || []).find((sj) => sj.job.id === liveView.jobId);
    return match ? `${match.job.title} at ${match.job.company}` : undefined;
  }, [liveView, session?.scored_jobs]);

  const quickActions = useMemo(() => {
    if(!session) return [];
    const role = session.keywords?.[0];
    const place = session.remote_only ? "remote" : session.locations?.[0];
    if(coachReviewOpen || session.status === "awaiting_coach_review") {
      return [
        "Explain the biggest changes to my resume",
        role ? `Tighten the resume for ${role} roles` : "Make the summary more specific",
      ];
    }
    if(shortlistReviewOpen || session.status === "awaiting_review") {
      return [
        "Why did these jobs make the shortlist?",
        place ? `Prefer roles in ${place}` : "Prefer larger companies",
      ];
    }
    if(TERMINAL.has(session.status)) {
      const kept = sessionSummary?.total_scored ?? session.scored_jobs?.length ?? 0;
      return kept === 0
        ? ["Which jobs came closest to the cutoff?", "What should I change to get a shortlist?"]
        : ["Summarize what was sent", "Which companies replied fastest last time?"].slice(0, 1);
    }
    if(session.status === "applying" || interventionData || submitConfirmData) {
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
    } catch(e) {
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
    } catch(e) {
      toast.error(e instanceof Error ? e.message : "Couldn't start the run.");
      setRunAction(null);
    }
  };

  const handleConfirmLogin = async () => {
    setLoginConfirming(true);
    try {
      await confirmLogin(sessionId);
      setLoginPrompt(null);
    } catch(e) {
      console.error("Failed to confirm login:", e);
    } finally {
      setLoginConfirming(false);
    }
  };
  return {
    sessionId,
    session,
    events,
    savedAnswerRules,
    saveAnswer,
    elapsedSeconds,
    coachReviewOpen,
    setCoachReviewOpen,
    coachReviewData,
    setCoachReviewData,
    coachReviewSubmitting,
    shortlistReviewOpen,
    setShortlistReviewOpen,
    shortlistJobs,
    selectedJobIds,
    selectedCompanyCounts,
    shortlistSubmitting,
    sessionSummary,
    interventionData,
    submitConfirmData,
    chatMessages,
    chatLoading,
    checkpoints,
    rewindLoading,
    liveView,
    setLiveView,
    liveViewJobLabel,
    sseConnected,
    sseFailCount,
    loginPrompt,
    loginConfirming,
    handleConfirmLogin,
    handleSendChat,
    handleApproveShortlist,
    toggleJobSelection,
    handleApproveCoachReview,
    handleResumeIntervention,
    handleSubmitDecision,
    handleLoadCheckpoints,
    handleRewind,
    sendSuggestedMessage,
    quickActions,
    stopOpen,
    setStopOpen,
    runAction,
    rerunOpen,
    setRerunOpen,
    adjustOpen,
    setAdjustOpen,
    handleStop,
    handlePause,
    handleResumeRun,
    handleRerun,
    coachChatMode: coachReviewOpen || latestStatusRef.current === "awaiting_coach_review",
  };
}

export type SessionRun = ReturnType<typeof useSessionRun>;
export type LoadedSessionRun = SessionRun & { session: SessionData };
