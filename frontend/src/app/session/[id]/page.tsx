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
import { getSession, connectSSE, connectWebSocket, sendSteer, submitReview } from "@/lib/api";

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
  coach_output?: {
    rewritten_resume: string;
    resume_score: { overall: number; breakdown: Record<string, number> };
    cover_letter_template: string;
    linkedin_advice: string[];
    confidence_message: string;
  };
  steering_mode: string;
  applications_used: number;
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
  agent_statuses?: Record<string, string>;
  keywords?: string[];
  locations?: string[];
};

const STATUS_LABELS: Record<string, string> = {
  intake: "Processing Input",
  coaching: "Career Coaching",
  discovering: "Discovering Jobs",
  scoring: "Scoring Matches",
  tailoring: "Tailoring Resumes",
  awaiting_review: "Awaiting Your Review",
  applying: "Applying to Jobs",
  paused: "Paused",
  takeover: "Manual Control",
  completed: "Session Complete",
  failed: "Session Failed",
};

const PIPELINE_STEPS = ["intake", "coaching", "discovering", "scoring", "tailoring", "awaiting_review", "applying", "completed"];

export default function SessionPage() {
  const params = useParams();
  const sessionId = params.id as string;

  const [session, setSession] = useState<SessionData | null>(null);
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [chatMessages, setChatMessages] = useState<Array<{ role: string; text: string }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [viewMode, setViewMode] = useState<"status" | "screenshot" | "takeover">("status");
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);

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

      // Skip duplicate ping events
      if (evt.event === "ping") return;

      setEvents((prev) => [...prev, evt]);

      // Update session from event data
      setSession((prev) => {
        if (!prev) return prev;
        const updates: Partial<SessionData> = {};
        if (evt.status) updates.status = evt.status;
        if (evt.coach_output) updates.coach_output = evt.coach_output as SessionData["coach_output"];
        if (Array.isArray(evt.keywords) && evt.keywords.length > 0) updates.keywords = evt.keywords;
        return { ...prev, ...updates };
      });

      // Auto-scroll events
      setTimeout(() => eventsEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    });
    return cleanup;
  }, [sessionId]);

  // WebSocket for screenshot feed
  useEffect(() => {
    if (viewMode !== "screenshot") return;

    const cleanup = connectWebSocket(sessionId, (data) => {
      if (data.type === "screenshot" && data.image) {
        setScreenshotUrl(`data:image/jpeg;base64,${data.image}`);
      }
      if (data.type === "chat" && data.message) {
        setChatMessages((prev) => [...prev, { role: "agent", text: data.message as string }]);
      }
    });
    return cleanup;
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

  const handleApproveJobs = async (jobIds: string[]) => {
    try {
      await submitReview(sessionId, { approved_job_ids: jobIds, feedback: "" });
      setSession((prev) => prev ? { ...prev, status: "applying" } : prev);
    } catch (e) {
      console.error("Failed to submit review:", e);
    }
  };

  const currentStepIndex = session ? PIPELINE_STEPS.indexOf(session.status) : 0;
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
          <Progress value={progressPct} className="flex-1" />
          <span className="text-xs text-zinc-500 whitespace-nowrap">
            Step {currentStepIndex + 1}/{PIPELINE_STEPS.length}
          </span>
        </div>
        <div className="max-w-5xl mx-auto flex justify-between mt-2">
          {PIPELINE_STEPS.map((step, i) => (
            <span
              key={step}
              className={`text-xs ${i <= currentStepIndex ? "text-zinc-900 dark:text-white font-medium" : "text-zinc-400"}`}
            >
              {step === "awaiting_review" ? "Review" : step.charAt(0).toUpperCase() + step.slice(1)}
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

          {/* Job shortlist (for review) */}
          {session.status === "awaiting_review" && session.scored_jobs && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Review Shortlist</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {session.scored_jobs.slice(0, 10).map((sj) => (
                  <div key={sj.job.id} className="border rounded p-2 text-xs">
                    <p className="font-medium">{sj.job.title}</p>
                    <p className="text-zinc-500">{sj.job.company} — {sj.job.location}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <Badge variant="secondary">{sj.score}/100</Badge>
                      <Badge variant="secondary">{sj.job.board}</Badge>
                    </div>
                  </div>
                ))}
                <Button
                  size="sm"
                  className="w-full mt-2"
                  onClick={() => handleApproveJobs(session.scored_jobs.map((sj) => sj.job.id))}
                >
                  Approve All & Start Applying
                </Button>
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
    </div>
  );
}
