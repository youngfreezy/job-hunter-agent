"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { CircularProgress } from "@/components/ui/circular-progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { CoachPanel } from "@/components/CoachPanel";
import { getSession, connectSSE, connectWebSocket, sendSteer, submitReview, submitCoachReview } from "@/lib/api";
import type { CoachOutput } from "@/lib/api";

type SessionData = {
  session_id: string;
  status: string;
  keywords: string[];
  scored_jobs: Array<{
    job: { id: string; title: string; company: string; location: string; url: string; board: string };
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
  steering_mode: string;
  applications_used: number;
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
  job: { id: string; title: string; company: string; location: string; url: string; board: string };
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
  // Coaching/discovery progress events
  step?: string;
  progress?: number;
  board?: string;
  count?: number;
};

const STATUS_LABELS: Record<string, string> = {
  intake: "Processing Input",
  coaching: "Career Coaching",
  awaiting_coach_review: "Review Resume",
  discovering: "Discovering Jobs",
  scoring: "Scoring Matches",
  tailoring: "Tailoring Resumes",
  awaiting_review: "Awaiting Your Review",
  applying: "Applying to Jobs",
  verifying: "Verifying Applications",
  reporting: "Generating Report",
  paused: "Paused",
  takeover: "Manual Control",
  completed: "Session Complete",
  failed: "Session Failed",
};

const PIPELINE_STEPS = ["intake", "coaching", "awaiting_coach_review", "discovering", "scoring", "tailoring", "awaiting_review", "applying", "verifying", "reporting", "completed"];

export default function SessionPage() {
  const params = useParams();
  const sessionId = params.id as string;

  const [session, setSession] = useState<SessionData | null>(null);
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [chatMessages, setChatMessages] = useState<Array<{ role: string; text: string }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [viewMode, setViewMode] = useState<"status" | "screenshot" | "takeover">("status");
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);
  const [coachReviewOpen, setCoachReviewOpen] = useState(false);
  const [coachReviewData, setCoachReviewData] = useState<CoachOutput | null>(null);
  const [coachReviewSubmitting, setCoachReviewSubmitting] = useState(false);
  const [shortlistReviewOpen, setShortlistReviewOpen] = useState(false);
  const [shortlistJobs, setShortlistJobs] = useState<ScoredJobData[]>([]);
  const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());
  const [shortlistSubmitting, setShortlistSubmitting] = useState(false);
  const [stepProgress, setStepProgress] = useState(0); // latest progress % from *_progress events
  const [sessionSummary, setSessionSummary] = useState<SessionSummaryData | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const eventsEndRef = useRef<HTMLDivElement>(null);

  // Load session — may 404 initially (pipeline hasn't checkpointed yet)
  useEffect(() => {
    getSession(sessionId)
      .then((data) => setSession(data as unknown as SessionData))
      .catch(() => {
        // Session not in checkpointer yet — set a minimal placeholder
        setSession({
          session_id: sessionId,
          status: "intake",
          keywords: [],
          scored_jobs: [],
          applications_submitted: [],
          applications_failed: [],
          steering_mode: "status",
          applications_used: 0,
        });
      });
  }, [sessionId]);

  // SSE connection
  useEffect(() => {
    const cleanup = connectSSE(sessionId, (event) => {
      const evt = event as unknown as SSEEvent;

      // Skip ping events
      if (evt.event === "ping") return;

      // Deduplicate: skip if last event has same type + same message/step
      setEvents((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.event === evt.event) {
          const lastKey = last.message || last.step || last.status || "";
          const evtKey = evt.message || evt.step || evt.status || "";
          if (lastKey && lastKey === evtKey) return prev;
        }
        return [...prev, evt];
      });

      // Track step progress from *_progress events
      if (evt.event?.endsWith("_progress") && typeof evt.progress === "number") {
        setStepProgress(evt.progress);
      }

      // Update session from event data
      setSession((prev) => {
        if (!prev) return prev;
        const updates: Partial<SessionData> = {};
        // Only update pipeline status from "status", "done", "coach_review", or "shortlist_review" events
        if (evt.status && (evt.event === "status" || evt.event === "done" || evt.event === "coach_review" || evt.event === "shortlist_review")) {
          updates.status = evt.status;
          // Reset step progress when status changes (new stage starting)
          setStepProgress(0);
        }
        if (evt.coach_output) updates.coach_output = evt.coach_output as unknown as SessionData["coach_output"];
        if (Array.isArray(evt.keywords) && evt.keywords.length > 0) updates.keywords = evt.keywords;
        return { ...prev, ...updates };
      });

      // Open coach review modal when the pipeline pauses for review.
      // Store the data always (for the sidebar), but only open the modal
      // if the session is still awaiting review (not if replaying old events).
      if (evt.event === "coach_review" && evt.coach_output) {
        const co = evt.coach_output as unknown as CoachOutput;
        setCoachReviewData(co);
        setSession((prev) => {
          // Only auto-open if we're still at coaching/awaiting_coach_review
          if (prev && (prev.status === "coaching" || prev.status === "awaiting_coach_review")) {
            setCoachReviewOpen(true);
          }
          return prev;
        });
      }
      // Close modal if pipeline has moved past coach review
      if (evt.event === "status" && evt.status && evt.status !== "coaching" && evt.status !== "awaiting_coach_review") {
        setCoachReviewOpen(false);
      }

      // Open shortlist review modal
      if (evt.event === "shortlist_review" && evt.scored_jobs) {
        const jobs = evt.scored_jobs as ScoredJobData[];
        setShortlistJobs(jobs);
        setSelectedJobIds(new Set(jobs.map((sj) => sj.job.id)));
        setSession((prev) => {
          if (prev && (prev.status === "tailoring" || prev.status === "awaiting_review")) {
            setShortlistReviewOpen(true);
          }
          return prev;
        });
      }
      // Close shortlist modal if pipeline moved past review
      if (evt.event === "status" && evt.status && evt.status !== "tailoring" && evt.status !== "awaiting_review") {
        setShortlistReviewOpen(false);
      }

      // Capture session summary from done event
      if (evt.event === "done" && evt.session_summary) {
        setSessionSummary(evt.session_summary);
      }

      // Auto-scroll events
      setTimeout(() => eventsEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    });
    return cleanup;
  }, [sessionId]);

  // WebSocket for screenshot feed + notify backend of mode switch
  useEffect(() => {
    if (viewMode !== "screenshot" && viewMode !== "takeover") return;

    // Tell the backend to enable screenshot streaming
    sendSteer(sessionId, { message: `Switched to ${viewMode} mode`, mode: viewMode }).catch(() => {});

    const cleanup = connectWebSocket(sessionId, (data) => {
      if (data.type === "screenshot" && data.image) {
        setScreenshotUrl(`data:image/jpeg;base64,${data.image}`);
      }
      if (data.type === "chat" && data.message) {
        setChatMessages((prev) => [...prev, { role: "agent", text: data.message as string }]);
      }
    });

    return () => {
      cleanup();
      // Revert to status mode when leaving screenshot/takeover
      sendSteer(sessionId, { message: "Switched back to status mode", mode: "status" }).catch(() => {});
    };
  }, [sessionId, viewMode]);

  const handleSendChat = useCallback(async () => {
    if (!chatInput.trim()) return;
    const msg = chatInput.trim();
    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", text: msg }]);
    try {
      await sendSteer(sessionId, { message: msg, mode: viewMode });
    } catch (e) {
      console.error("Failed to send steering message:", e);
    }
  }, [chatInput, sessionId, viewMode]);

  const handleApproveShortlist = async () => {
    setShortlistSubmitting(true);
    try {
      const jobIds = Array.from(selectedJobIds);
      await submitReview(sessionId, { approved_job_ids: jobIds, feedback: "" });
      setShortlistReviewOpen(false);
      setSession((prev) => prev ? { ...prev, status: "applying" } : prev);
    } catch (e) {
      console.error("Failed to submit review:", e);
    } finally {
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
      setCoachReviewOpen(false);
      setSession((prev) => prev ? { ...prev, status: "discovering" } : prev);
    } catch (e) {
      console.error("Failed to submit coach review:", e);
    } finally {
      setCoachReviewSubmitting(false);
    }
  };

  const rawStepIndex = session ? PIPELINE_STEPS.indexOf(session.status) : 0;
  const currentStepIndex = Math.max(0, rawStepIndex); // -1 → 0 for unknown statuses
  const progressPct = session ? Math.max(5, ((currentStepIndex + 1) / PIPELINE_STEPS.length) * 100) : 0;

  if (!session) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-zinc-500">Loading session...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950 flex flex-col">
      {/* Nav */}
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-3 flex items-center justify-between">
        <Link href="/" className="text-lg font-bold">JobHunter Agent</Link>
        <div className="flex items-center gap-3">
          <Badge variant={session.status === "completed" ? "default" : "secondary"}>
            {STATUS_LABELS[session.status] || session.status}
          </Badge>
          <Link href="/dashboard">
            <Button variant="outline" size="sm">Dashboard</Button>
          </Link>
        </div>
      </nav>

      {/* Progress bar */}
      <div className="px-6 py-3 border-b border-zinc-100 dark:border-zinc-900">
        <div className="max-w-5xl mx-auto flex items-center gap-4">
          <Progress value={progressPct} className={`flex-1 ${session.status !== "completed" && session.status !== "failed" ? "[&>div]:animate-progress-pulse" : ""}`} />
          {session.status !== "completed" && session.status !== "failed" ? (
            <CircularProgress value={stepProgress} size={36} strokeWidth={3} showValue pulse />
          ) : (
            <span className="text-xs text-zinc-500 whitespace-nowrap">
              {session.status === "completed" ? "Done" : "Failed"}
            </span>
          )}
        </div>
        <div className="max-w-5xl mx-auto flex justify-between mt-2">
          {PIPELINE_STEPS.map((step, i) => (
            <span
              key={step}
              className={`text-xs ${i <= currentStepIndex ? "text-zinc-900 dark:text-white font-medium" : "text-zinc-400"}`}
            >
              {step === "awaiting_review" ? "Review" : step === "awaiting_coach_review" ? "Coach Review" : step.charAt(0).toUpperCase() + step.slice(1)}
            </span>
          ))}
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex max-w-7xl mx-auto w-full">
        {/* Left: Viewer */}
        <div className="flex-1 p-4 flex flex-col">
          <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as typeof viewMode)} className="flex-1 flex flex-col">
            <TabsList className="mb-3">
              <TabsTrigger value="status">Status Feed</TabsTrigger>
              <TabsTrigger value="screenshot">Screenshot Feed</TabsTrigger>
              <TabsTrigger value="takeover">Take Control</TabsTrigger>
            </TabsList>

            <TabsContent value="status" className="flex-1 flex flex-col">
              <Card className="flex-1 flex flex-col">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Live Status</CardTitle>
                </CardHeader>
                <CardContent className="flex-1 overflow-y-auto max-h-[500px] space-y-2 font-mono text-sm">
                  {events.length === 0 && (
                    <p className="text-zinc-400">Waiting for events...</p>
                  )}
                  {events.map((evt, i) => {
                    const time = evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : "";

                    // Progress events get special rendering (any *_progress event)
                    if (evt.event?.endsWith("_progress")) {
                      const label = evt.event.replace("_progress", "");
                      const pct = typeof evt.progress === "number" ? evt.progress : undefined;
                      return (
                        <div key={i} className="flex items-center gap-2">
                          <span className="text-zinc-400 text-xs whitespace-nowrap">{time}</span>
                          <Badge variant="secondary" className="text-xs">{label}</Badge>
                          <span className="text-blue-600 dark:text-blue-400">{evt.step}</span>
                          {pct !== undefined && pct >= 0 && (
                            <CircularProgress value={pct} size={24} strokeWidth={2.5} showValue className="ml-auto" />
                          )}
                        </div>
                      );
                    }

                    const agent = evt.agent || evt.event || "system";
                    const msg = evt.message
                      || (evt.event === "discovery" ? `Found ${evt.jobs_found ?? 0} jobs so far` : "")
                      || (evt.event === "scoring" ? `Scored ${evt.scored_count ?? 0} jobs` : "")
                      || (evt.event === "agent_complete" ? `${agent} completed` : "")
                      || evt.status
                      || evt.event;
                    return (
                      <div key={i} className="flex gap-2">
                        <span className="text-zinc-400 text-xs whitespace-nowrap">{time}</span>
                        <Badge variant="secondary" className="text-xs">{agent}</Badge>
                        <span className={evt.event === "error" ? "text-red-500" : ""}>{msg}</span>
                      </div>
                    );
                  })}
                  <div ref={eventsEndRef} />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="screenshot" className="flex-1 flex flex-col">
              <Card className="flex-1 flex flex-col">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Live Screenshot Feed</CardTitle>
                </CardHeader>
                <CardContent className="flex-1 flex items-center justify-center bg-zinc-100 dark:bg-zinc-900 rounded min-h-[400px]">
                  {screenshotUrl ? (
                    <img src={screenshotUrl} alt="Browser" className="max-w-full max-h-full object-contain" />
                  ) : (
                    <div className="text-center text-zinc-400">
                      <p className="text-lg mb-2">Screenshot Feed</p>
                      <p className="text-sm">Connecting to browser session...</p>
                    </div>
                  )}
                  <canvas ref={canvasRef} className="hidden" />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="takeover" className="flex-1 flex flex-col">
              <Card className="flex-1 flex flex-col">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Browser Control (noVNC)</CardTitle>
                </CardHeader>
                <CardContent className="flex-1 flex items-center justify-center bg-zinc-100 dark:bg-zinc-900 rounded min-h-[400px]">
                  <div className="text-center text-zinc-400">
                    <p className="text-lg mb-2">Direct Browser Control</p>
                    <p className="text-sm mb-4">Take direct control of the browser when the agent needs help.</p>
                    <Button variant="outline">Request Control</Button>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>

          {/* Chat panel (visible in screenshot and takeover modes) */}
          {(viewMode === "screenshot" || viewMode === "takeover") && (
            <Card className="mt-3">
              <CardContent className="p-3">
                <div className="max-h-32 overflow-y-auto mb-2 space-y-1">
                  {chatMessages.map((msg, i) => (
                    <div key={i} className={`text-sm ${msg.role === "user" ? "text-blue-600" : "text-zinc-600"}`}>
                      <span className="font-medium">{msg.role === "user" ? "You" : "Agent"}:</span> {msg.text}
                    </div>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Input
                    placeholder="Steer the agent... e.g. 'Skip this job' or 'Use a different answer'"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSendChat()}
                  />
                  <Button size="sm" onClick={handleSendChat}>Send</Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right: Sidebar */}
        <div className="w-80 border-l border-zinc-200 dark:border-zinc-800 p-4 space-y-4 overflow-y-auto">
          {/* Session info */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Session</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <p><span className="text-zinc-500">Keywords:</span> {session.keywords?.join(", ")}</p>
              <p><span className="text-zinc-500">Applications:</span> {session.applications_used || 0}</p>
              <p><span className="text-zinc-500">Submitted:</span> {session.applications_submitted?.length || 0}</p>
              <p><span className="text-zinc-500">Failed:</span> {session.applications_failed?.length || 0}</p>
            </CardContent>
          </Card>

          {/* Coach output */}
          {session.coach_output && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Career Coach</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-zinc-500">Resume Score:</span>
                  <Badge>{session.coach_output.resume_score.overall}/100</Badge>
                </div>
                <p className="text-zinc-600 dark:text-zinc-400 italic text-xs">
                  {session.coach_output.confidence_message?.slice(0, 120)}...
                </p>
              </CardContent>
            </Card>
          )}

          {/* Shortlist summary (shown when review data is available) */}
          {shortlistJobs.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Shortlist</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <p><span className="text-zinc-500">Jobs scored:</span> {shortlistJobs.length}</p>
                <p><span className="text-zinc-500">Top score:</span> {shortlistJobs[0]?.score}/100</p>
                {session.status === "awaiting_review" && (
                  <Button size="sm" className="w-full mt-2" onClick={() => setShortlistReviewOpen(true)}>
                    Review Shortlist
                  </Button>
                )}
              </CardContent>
            </Card>
          )}

          {/* Session Summary (shown when completed) */}
          {sessionSummary && session.status === "completed" && (
            <Card className="border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-green-800 dark:text-green-200">Session Complete</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="grid grid-cols-2 gap-1">
                  <span className="text-zinc-500">Discovered:</span>
                  <span className="font-medium">{sessionSummary.total_discovered}</span>
                  <span className="text-zinc-500">Scored:</span>
                  <span className="font-medium">{sessionSummary.total_scored}</span>
                  <span className="text-zinc-500">Applied:</span>
                  <span className="font-medium text-green-700 dark:text-green-300">{sessionSummary.total_applied}</span>
                  <span className="text-zinc-500">Failed:</span>
                  <span className="font-medium text-red-600">{sessionSummary.total_failed}</span>
                  <span className="text-zinc-500">Skipped:</span>
                  <span className="font-medium">{sessionSummary.total_skipped}</span>
                  <span className="text-zinc-500">Avg Fit:</span>
                  <span className="font-medium">{sessionSummary.avg_fit_score}/100</span>
                  <span className="text-zinc-500">Duration:</span>
                  <span className="font-medium">{sessionSummary.duration_minutes}m</span>
                </div>
                {sessionSummary.top_companies.length > 0 && (
                  <div>
                    <p className="text-zinc-500 text-xs mb-1">Top Companies:</p>
                    <div className="flex flex-wrap gap-1">
                      {sessionSummary.top_companies.slice(0, 5).map((c, i) => (
                        <Badge key={i} variant="secondary" className="text-xs">{c}</Badge>
                      ))}
                    </div>
                  </div>
                )}
                {sessionSummary.next_steps.length > 0 && (
                  <div>
                    <p className="text-zinc-500 text-xs mb-1">Next Steps:</p>
                    <ul className="space-y-1">
                      {sessionSummary.next_steps.map((step, i) => (
                        <li key={i} className="text-xs text-zinc-700 dark:text-zinc-300">
                          {i + 1}. {step}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Application log */}
          {session.applications_submitted && session.applications_submitted.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Applications</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-xs max-h-64 overflow-y-auto">
                {session.applications_submitted.map((app, i) => (
                  <div key={i} className="flex items-center gap-2 py-1 border-b border-zinc-100 dark:border-zinc-800 last:border-0">
                    <span className="text-green-600">✓</span>
                    <span className="truncate">{app.job_id.slice(0, 8)}...</span>
                    <Badge variant="secondary" className="text-xs">{app.status}</Badge>
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
            <DialogTitle>Review Your Coached Resume</DialogTitle>
            <DialogDescription>
              The Career Coach has analyzed and rewritten your resume. Review the results below, then approve to continue to job discovery.
            </DialogDescription>
          </DialogHeader>
          {coachReviewData && (
            <CoachPanel coach={coachReviewData} />
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
              disabled={coachReviewSubmitting}
            >
              {coachReviewSubmitting ? "Approving..." : "Approve & Start Job Discovery"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Shortlist Review Modal */}
      <Dialog open={shortlistReviewOpen} onOpenChange={setShortlistReviewOpen}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Review Job Shortlist</DialogTitle>
            <DialogDescription>
              Select the jobs you want to apply to. Tailored resumes have been prepared for each one. Deselect any you want to skip.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 max-h-[55vh] overflow-y-auto">
            {shortlistJobs.map((sj) => {
              const selected = selectedJobIds.has(sj.job.id);
              return (
                <div
                  key={sj.job.id}
                  className={`border rounded-lg p-3 cursor-pointer transition-colors ${
                    selected
                      ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
                      : "border-zinc-200 dark:border-zinc-800 opacity-60"
                  }`}
                  onClick={() => toggleJobSelection(sj.job.id)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="font-medium text-sm">{sj.job.title}</p>
                      <p className="text-xs text-zinc-500">{sj.job.company} — {sj.job.location}</p>
                      {sj.reasons && sj.reasons.length > 0 && (
                        <ul className="mt-1 space-y-0.5">
                          {sj.reasons.map((r, ri) => (
                            <li key={ri} className="text-xs text-zinc-600 dark:text-zinc-400">- {r}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                    <div className="flex items-center gap-2 ml-3">
                      <CircularProgress value={sj.score} size={36} strokeWidth={3} showValue />
                      <Badge variant="secondary" className="text-xs">{sj.job.board}</Badge>
                      <div className={`w-5 h-5 rounded border-2 flex items-center justify-center ${
                        selected ? "border-blue-500 bg-blue-500 text-white" : "border-zinc-300"
                      }`}>
                        {selected && <span className="text-xs">✓</span>}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <DialogFooter className="flex items-center justify-between">
            <span className="text-sm text-zinc-500">
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
                disabled={shortlistSubmitting || selectedJobIds.size === 0}
              >
                {shortlistSubmitting ? "Submitting..." : `Apply to ${selectedJobIds.size} Jobs`}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
