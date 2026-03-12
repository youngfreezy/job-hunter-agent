// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  connectTrialSSE,
  getTrialToken,
  getTrialEmail,
  convertTrialAccount,
  clearTrialData,
} from "@/lib/api";

type EventEntry = {
  event: string;
  timestamp: string;
  [key: string]: unknown;
};

const STATUS_LABELS: Record<string, string> = {
  intake: "Setting things up",
  coaching: "Analyzing your resume",
  discovering: "Searching job boards",
  scoring: "Scoring job matches",
  tailoring: "Tailoring your resume",
  applying: "Applying to jobs",
  done: "Complete!",
  error: "Error",
};

const STATUS_DESCRIPTIONS: Record<string, string> = {
  intake: "Preparing your job search profile...",
  coaching: "Our AI is reviewing your experience and skills to find the best matches.",
  discovering: "Scanning thousands of listings across top job boards in real time.",
  scoring: "Ranking every job against your resume for the best fit.",
  tailoring: "Customizing your resume for each top-scored position.",
  applying: "Submitting applications to your best-matched jobs.",
  done: "All done! Your applications have been submitted.",
  error: "Something went wrong. Please try again.",
};

const STEP_LABELS: Record<string, string> = {
  intake: "Setup",
  coaching: "Analyze",
  discovering: "Search",
  scoring: "Rank",
  tailoring: "Tailor",
  applying: "Apply",
  done: "Done",
};

const STATUS_ORDER = ["intake", "coaching", "discovering", "scoring", "tailoring", "applying", "done"];

export default function TrialSessionPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;

  const [events, setEvents] = useState<EventEntry[]>([]);
  const [status, setStatus] = useState("intake");
  const [connected, setConnected] = useState(false);
  const [showConvert, setShowConvert] = useState(false);
  const [convertError, setConvertError] = useState("");
  const [converting, setConverting] = useState(false);
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");

  // Stats
  const [discovered, setDiscovered] = useState(0);
  const [scored, setScored] = useState(0);
  const [submitted, setSubmitted] = useState(0);
  const [failed, setFailed] = useState(0);

  const trialEmail = getTrialEmail();
  const cleanupRef = useRef<(() => void) | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const token = getTrialToken();
    if (!token) {
      router.replace("/try");
      return;
    }

    const cleanup = connectTrialSSE(
      sessionId,
      (event) => {
        const entry = event as EventEntry;
        setEvents((prev) => [...prev.slice(-100), entry]);

        // Update status
        if (entry.event === "status" && typeof entry.status === "string") {
          setStatus(entry.status);
        }
        if (entry.event === "done") {
          setStatus("done");
          setTimeout(() => setShowConvert(true), 1500);
        }
        if (entry.event === "error") {
          setStatus("error");
        }

        // Update stats
        if (entry.event === "discovery_progress") {
          const t = entry.total as number;
          if (typeof t === "number" && t > 0) setDiscovered(t);
        }
        if (entry.event === "scoring_progress") {
          const s = (entry.scored as number) ?? (entry.scored_so_far as number);
          if (typeof s === "number") setScored(s);
        }
        // Use only absolute counts from application_progress summary events.
        // Incremental counters (s + 1) from application_submitted/failed
        // double-count on SSE reconnect since all events are replayed.
        if (
          entry.event === "application_progress" &&
          (typeof entry.submitted === "number" ||
            typeof entry.failed === "number" ||
            typeof entry.skipped === "number")
        ) {
          const sub = typeof entry.submitted === "number" ? entry.submitted : 0;
          const fail = typeof entry.failed === "number" ? entry.failed : 0;
          const skip = typeof entry.skipped === "number" ? entry.skipped : 0;
          setSubmitted(sub);
          setFailed(fail + skip);
        }
      },
      setConnected,
    );
    cleanupRef.current = cleanup;

    return () => {
      cleanup();
    };
  }, [sessionId, router]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  const currentStepIdx = STATUS_ORDER.indexOf(status);

  const handleConvert = async () => {
    const token = getTrialToken();
    if (!token) return;
    if (password.length < 8) {
      setConvertError("Password must be at least 8 characters");
      return;
    }
    setConverting(true);
    setConvertError("");
    try {
      await convertTrialAccount({ trial_token: token, password, name: name || undefined });
      clearTrialData();
      // Redirect to sign in so they can log in with their new credentials
      router.push("/auth/signin?converted=true");
    } catch (err) {
      setConvertError(err instanceof Error ? err.message : "Conversion failed");
    } finally {
      setConverting(false);
    }
  };

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <Link href="/" className="text-lg font-bold text-zinc-900 dark:text-white">
            JobHunter Agent
          </Link>
          <div className="flex items-center gap-3">
            <span className="inline-block bg-green-100 text-green-800 text-xs font-medium px-2 py-0.5 rounded-full dark:bg-green-900/40 dark:text-green-300">
              Free Trial
            </span>
            <span className={`w-2 h-2 rounded-full ${connected ? "bg-green-500" : "bg-red-500"}`} />
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-10">
        <h1 className="text-2xl font-bold text-zinc-900 dark:text-white mb-1">
          {status === "done" ? "Session Complete!" : "Your AI Job Hunt is in Progress"}
        </h1>
        {status !== "done" && (
          <div className="mb-6">
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {STATUS_DESCRIPTIONS[status] || "Working on it..."}
            </p>
            <p className="text-sm text-zinc-400 dark:text-zinc-500 mt-1">
              Feel free to step away — this typically takes 15-20 minutes. We&apos;ll email you when it&apos;s done.
            </p>
          </div>
        )}
        {status === "done" && <div className="mb-6" />}

        {/* Progress pipeline */}
        <div className="flex items-center gap-0.5 mb-8">
          {STATUS_ORDER.map((step, i) => {
            const isCompleted = i < currentStepIdx;
            const isCurrent = step === status;
            const isFailed = status === "error" && isCurrent;
            return (
              <div key={step} className="flex items-center flex-1 last:flex-none">
                {/* Step pill */}
                <div
                  className={`
                    relative flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-medium transition-all duration-500 whitespace-nowrap overflow-hidden
                    ${
                      isCompleted
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-900/60 dark:text-blue-300"
                        : isFailed
                        ? "bg-red-500 text-white shadow-lg shadow-red-500/30"
                        : isCurrent
                        ? "bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/30"
                        : "text-zinc-400 dark:text-zinc-500"
                    }
                  `}
                >
                  {isCurrent && !isFailed && (
                    <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-[gradient-shift_2s_ease_infinite] bg-[length:200%_100%]" />
                  )}
                  {isCompleted ? (
                    <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  ) : isCurrent && !isFailed ? (
                    <span className="relative flex h-2 w-2 shrink-0">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-white" />
                    </span>
                  ) : (
                    <span className="w-1.5 h-1.5 rounded-full bg-current opacity-30 shrink-0" />
                  )}
                  <span className="relative z-10">{STEP_LABELS[step] || step}</span>
                </div>
                {/* Connector */}
                {i < STATUS_ORDER.length - 1 && (
                  <div className="flex-1 mx-0.5">
                    <div className="h-0.5 w-full rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ease-out ${
                          isFailed ? "bg-red-400" : "bg-blue-500"
                        }`}
                        style={{ width: isCompleted ? "100%" : isCurrent ? "50%" : "0%" }}
                      />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Stats cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <StatCard label="Jobs Found" value={discovered} />
          <StatCard label="Scored" value={scored} />
          <StatCard label="Applied" value={submitted} color="green" />
          <StatCard label="Skipped" value={failed} color="red" />
        </div>

        {/* Event log */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Activity Log</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {events.length === 0 && (
                <p className="text-sm text-zinc-400">Waiting for events...</p>
              )}
              {events.filter((e) => !["agent_complete", "scoring", "discovery"].includes(e.event)).slice(-50).map((e, i) => (
                <div key={i} className="flex items-start gap-3 text-sm">
                  <span className="text-xs text-zinc-400 mt-0.5 whitespace-nowrap font-mono">
                    {new Date(e.timestamp).toLocaleTimeString()}
                  </span>
                  <EventBadge event={e.event} />
                  <span className="text-zinc-700 dark:text-zinc-300 min-w-0">
                    {formatEvent(e)}
                  </span>
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </CardContent>
        </Card>

        {/* Conversion prompt (inline, always visible after done) */}
        {status === "done" && !showConvert && (
          <div className="mt-6 text-center">
            <Button onClick={() => setShowConvert(true)} size="lg">
              Create Account to See Full Results
            </Button>
          </div>
        )}
      </div>

      {/* Conversion modal */}
      <Dialog open={showConvert} onOpenChange={setShowConvert}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Your applications are in!</DialogTitle>
            <DialogDescription>
              Create an account to track responses, run more sessions, and enable email
              auto-verification.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-lg bg-green-50 dark:bg-green-950/30 p-3 text-center">
                <p className="text-2xl font-bold text-green-700 dark:text-green-400">{submitted}</p>
                <p className="text-xs text-green-600 dark:text-green-500">Applied</p>
              </div>
              <div className="rounded-lg bg-blue-50 dark:bg-blue-950/30 p-3 text-center">
                <p className="text-2xl font-bold text-blue-700 dark:text-blue-400">{discovered}</p>
                <p className="text-xs text-blue-600 dark:text-blue-500">Jobs Found</p>
              </div>
            </div>

            <div>
              <label className="text-sm font-medium block mb-1">Email</label>
              <input
                type="email"
                value={trialEmail || ""}
                disabled
                className="w-full px-3 py-2 rounded-lg border bg-zinc-50 text-sm dark:bg-zinc-900 dark:border-zinc-800"
              />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Your name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Jane Doe"
                className="w-full px-3 py-2 rounded-lg border text-sm dark:bg-zinc-900 dark:border-zinc-800"
              />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Create a password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                className="w-full px-3 py-2 rounded-lg border text-sm dark:bg-zinc-900 dark:border-zinc-800"
              />
            </div>

            {convertError && (
              <p className="text-xs text-red-600">{convertError}</p>
            )}
          </div>
          <DialogFooter className="flex-col gap-2 sm:flex-col">
            <Button onClick={handleConvert} disabled={converting} className="w-full">
              {converting ? "Creating account..." : "Create Account"}
            </Button>
            <button
              type="button"
              onClick={() => setShowConvert(false)}
              className="text-xs text-zinc-500 hover:text-zinc-700"
            >
              Maybe later
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color?: string }) {
  const textColor =
    color === "green"
      ? "text-green-700 dark:text-green-400"
      : color === "red"
      ? "text-red-600 dark:text-red-400"
      : "text-zinc-900 dark:text-white";

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 p-4 text-center">
      <p className={`text-2xl font-bold ${textColor}`}>{value}</p>
      <p className="text-xs text-zinc-500 mt-1">{label}</p>
    </div>
  );
}

function EventBadge({ event }: { event: string }) {
  const colors: Record<string, string> = {
    status: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
    discovery_progress: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
    scoring_progress: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
    tailoring_progress: "bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300",
    application_progress: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
    application_submitted: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
    application_failed: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
    application_start: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
    coaching_progress: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
    verification_progress: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    reporting_progress: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300",
    error: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
    done: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  };

  const labels: Record<string, string> = {
    application_submitted: "applied",
    application_failed: "skipped",
    application_start: "applying",
    application_progress: "applying",
    verification_progress: "verifying",
    reporting_progress: "report",
  };

  return (
    <span className={`flex-shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded ${colors[event] || "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"}`}>
      {labels[event] || event.replace(/_/g, " ")}
    </span>
  );
}

function formatEvent(e: EventEntry): string {
  if (e.event === "status") return STATUS_LABELS[e.status as string] || String(e.status);
  if (e.event === "discovery_progress") return (e.step as string) || `Found ${e.total} jobs on ${e.board || "job boards"}`;
  if (e.event === "scoring_progress") return (e.step as string) || `Scored ${e.scored_so_far ?? e.scored ?? "?"} jobs`;
  if (e.event === "tailoring_progress") return `Tailored resume ${e.current}/${e.total}`;
  if (e.event === "application_progress") {
    if (e.step) return String(e.step);
    const company = (e.company as string) || (e.job_title as string) || "";
    if (company) return `Processing ${company}`;
    return "Processing applications...";
  }
  if (e.event === "application_start") {
    const company = (e.company as string) || (e.job_title as string) || "";
    return `Starting application: ${company} (${e.current}/${e.total})`;
  }
  if (e.event === "application_submitted") {
    return `Applied to ${(e.company as string) || (e.job_title as string) || "job"}`;
  }
  if (e.event === "application_failed") {
    const company = (e.company as string) || (e.job_title as string) || "";
    return `Skipped ${company}: ${e.error || "could not complete"}`;
  }
  if (e.event === "verification_progress") return (e.step as string) || "Verifying submissions...";
  if (e.event === "reporting_progress") return (e.step as string) || "Generating report...";
  if (e.event === "coaching_progress") return String(e.message || "Analyzing resume...");
  if (e.event === "done") return "Session complete!";
  if (e.event === "error") return String(e.message || e.error || "An error occurred");
  return String(e.message || e.step || e.event.replace(/_/g, " "));
}
