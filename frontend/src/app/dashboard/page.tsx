"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { listSessions, type SessionListItem } from "@/lib/api";

const STATUS_LABELS: Record<string, string> = {
  intake: "Starting",
  coaching: "Coaching",
  discovering: "Discovering",
  scoring: "Scoring",
  tailoring: "Tailoring",
  applying: "Applying",
  awaiting_coach_review: "Needs Coach Review",
  awaiting_review: "Needs Shortlist Review",
  needs_intervention: "Needs Intervention",
  paused: "Paused",
  completed: "Completed",
  failed: "Failed",
};

const STATUS_COLORS: Record<string, "default" | "secondary" | "destructive" | "outline"> =
  {
    completed: "default",
    applying: "secondary",
    failed: "destructive",
    paused: "outline",
    intake: "outline",
    coaching: "secondary",
    discovering: "secondary",
    scoring: "secondary",
    tailoring: "secondary",
    awaiting_coach_review: "outline",
    awaiting_review: "outline",
    needs_intervention: "destructive",
  };

const ACTION_REQUIRED = new Set([
  "awaiting_coach_review",
  "awaiting_review",
  "needs_intervention",
  "paused",
]);

function formatRelativeDate(value: string) {
  const date = new Date(value);
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function getSessionHeadline(session: SessionListItem) {
  if (session.status === "awaiting_coach_review") {
    return "Resume rewrite is waiting for approval";
  }
  if (session.status === "awaiting_review") {
    return "Shortlist is ready for approval";
  }
  if (session.status === "needs_intervention") {
    return "Application flow is blocked and needs manual help";
  }
  if (session.status === "paused") {
    return "Workflow paused. Resume when you are ready.";
  }
  if (session.status === "completed") {
    return "Session complete. Review results and proofs.";
  }
  if (session.status === "failed") {
    return "A failure stopped the session. Inspect the log before retrying.";
  }
  return "Automation is running with live updates and operator controls.";
}

export default function Dashboard() {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listSessions()
      .then(setSessions)
      .catch((err) => console.error("Failed to load sessions:", err))
      .finally(() => setLoading(false));
  }, []);

  const sortedSessions = useMemo(() => {
    return [...sessions].sort((a, b) => {
      const aPriority = ACTION_REQUIRED.has(a.status) ? 0 : a.status === "applying" ? 1 : 2;
      const bPriority = ACTION_REQUIRED.has(b.status) ? 0 : b.status === "applying" ? 1 : 2;
      if (aPriority !== bPriority) return aPriority - bPriority;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  }, [sessions]);

  const actionRequiredSessions = sortedSessions.filter((session) =>
    ACTION_REQUIRED.has(session.status)
  );
  const activeSessions = sortedSessions.filter(
    (session) =>
      !ACTION_REQUIRED.has(session.status) &&
      !["completed", "failed"].includes(session.status)
  );
  const completedSessions = sortedSessions.filter((session) =>
    ["completed", "failed"].includes(session.status)
  );

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      <nav className="border-b border-zinc-200 px-6 py-4 dark:border-zinc-800">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <Link href="/" className="text-xl font-bold tracking-tight">
            JobHunter Agent
          </Link>
          <div className="flex items-center gap-4">
            <span className="text-sm text-zinc-500">test@example.com</span>
            <Link href="/session/new">
              <Button size="sm">New Session</Button>
            </Link>
          </div>
        </div>
      </nav>

      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <Card className="border-zinc-200 dark:border-zinc-800">
            <CardContent className="flex flex-col gap-5 p-8">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-sm font-medium uppercase tracking-[0.22em] text-zinc-500">
                    Dashboard
                  </p>
                  <h1 className="mt-2 text-4xl font-bold tracking-tight">
                    Keep sessions moving without losing context
                  </h1>
                  <p className="mt-3 max-w-2xl text-zinc-600 dark:text-zinc-400">
                    Sessions that need your attention are surfaced first. Active
                    runs, completed runs, and blocked runs are separated so you
                    can decide quickly what to do next.
                  </p>
                </div>
                <Link href="/session/new">
                  <Button size="lg">Start New Session</Button>
                </Link>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/30">
                  <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
                    Needs attention
                  </p>
                  <p className="mt-2 text-3xl font-bold text-amber-900 dark:text-amber-100">
                    {actionRequiredSessions.length}
                  </p>
                  <p className="mt-1 text-sm text-amber-700 dark:text-amber-400">
                    Coach review, shortlist review, pauses, or manual intervention.
                  </p>
                </div>
                <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950/30">
                  <p className="text-sm font-medium text-blue-800 dark:text-blue-300">
                    In progress
                  </p>
                  <p className="mt-2 text-3xl font-bold text-blue-900 dark:text-blue-100">
                    {activeSessions.length}
                  </p>
                  <p className="mt-1 text-sm text-blue-700 dark:text-blue-400">
                    Sessions currently coaching, discovering, tailoring, or applying.
                  </p>
                </div>
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-900 dark:bg-emerald-950/30">
                  <p className="text-sm font-medium text-emerald-800 dark:text-emerald-300">
                    Applications sent
                  </p>
                  <p className="mt-2 text-3xl font-bold text-emerald-900 dark:text-emerald-100">
                    {sessions.reduce((sum, session) => sum + session.applications_submitted, 0)}
                  </p>
                  <p className="mt-1 text-sm text-emerald-700 dark:text-emerald-400">
                    Successful submissions across every session in the workspace.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-zinc-200 dark:border-zinc-800">
            <CardHeader>
              <CardTitle className="text-lg">Action Queue</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading ? (
                [1, 2, 3].map((item) => (
                  <div
                    key={item}
                    className="h-16 rounded-2xl bg-zinc-100 animate-pulse dark:bg-zinc-900"
                  />
                ))
              ) : actionRequiredSessions.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-zinc-300 p-5 text-sm text-zinc-500 dark:border-zinc-700">
                  No sessions are blocked right now. Start a new session or
                  check active runs for progress.
                </div>
              ) : (
                actionRequiredSessions.map((session) => (
                  <Link
                    key={session.session_id}
                    href={`/session/${session.session_id}`}
                    className="block rounded-2xl border border-zinc-200 p-4 transition-colors hover:border-zinc-400 dark:border-zinc-800 dark:hover:border-zinc-600"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <Badge
                          variant={STATUS_COLORS[session.status] || "secondary"}
                        >
                          {STATUS_LABELS[session.status] || session.status}
                        </Badge>
                        <p className="mt-2 font-medium">
                          {session.keywords.join(", ")}
                        </p>
                        <p className="mt-1 text-sm text-zinc-500">
                          {getSessionHeadline(session)}
                        </p>
                      </div>
                      <span className="text-xs text-zinc-500">
                        {formatRelativeDate(session.created_at)}
                      </span>
                    </div>
                  </Link>
                ))
              )}
            </CardContent>
          </Card>
        </div>

        <div className="mt-10 space-y-10">
          <section>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-semibold">Active Sessions</h2>
                <p className="text-sm text-zinc-500">
                  Runs that are currently moving through discovery or apply.
                </p>
              </div>
            </div>
            {loading ? (
              <div className="space-y-3">
                {[1, 2].map((item) => (
                  <div
                    key={item}
                    className="h-24 rounded-2xl bg-zinc-100 animate-pulse dark:bg-zinc-900"
                  />
                ))}
              </div>
            ) : activeSessions.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center">
                  <p className="text-lg font-medium">No active sessions</p>
                  <p className="mt-2 text-sm text-zinc-500">
                    Start a new session to begin discovery, coaching, and
                    applications.
                  </p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {activeSessions.map((session) => (
                  <SessionCard key={session.session_id} session={session} />
                ))}
              </div>
            )}
          </section>

          <section>
            <div className="mb-4">
              <h2 className="text-xl font-semibold">Completed And Historical</h2>
              <p className="text-sm text-zinc-500">
                Finished or failed sessions kept for audit and replay.
              </p>
            </div>
            {loading ? (
              <div className="space-y-3">
                {[1, 2].map((item) => (
                  <div
                    key={item}
                    className="h-24 rounded-2xl bg-zinc-100 animate-pulse dark:bg-zinc-900"
                  />
                ))}
              </div>
            ) : completedSessions.length === 0 ? (
              <Card>
                <CardContent className="py-10 text-center text-sm text-zinc-500">
                  No completed sessions yet.
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {completedSessions.map((session) => (
                  <SessionCard key={session.session_id} session={session} />
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function SessionCard({ session }: { session: SessionListItem }) {
  const submitted = session.applications_submitted;
  const failed = session.applications_failed;

  return (
    <Link href={`/session/${session.session_id}`} className="block">
      <Card className="border-zinc-200 transition-colors hover:border-zinc-400 dark:border-zinc-800 dark:hover:border-zinc-600">
        <CardContent className="py-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={STATUS_COLORS[session.status] || "secondary"}>
                  {STATUS_LABELS[session.status] || session.status}
                </Badge>
                <span className="text-sm text-zinc-500">
                  {formatRelativeDate(session.created_at)}
                </span>
                {session.remote_only && (
                  <Badge variant="outline">Remote only</Badge>
                )}
              </div>
              <p className="mt-3 text-lg font-semibold">
                {session.keywords.join(", ")}
              </p>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {getSessionHeadline(session)}
              </p>
              {session.locations.length > 0 && (
                <p className="mt-2 text-sm text-zinc-500">
                  Targeting {session.locations.join(", ")}
                </p>
              )}
            </div>
            <div className="grid min-w-[220px] grid-cols-3 gap-2 text-center">
              <div className="rounded-2xl bg-zinc-50 px-3 py-3 dark:bg-zinc-900">
                <p className="text-xl font-bold text-emerald-600">{submitted}</p>
                <p className="text-xs text-zinc-500">Submitted</p>
              </div>
              <div className="rounded-2xl bg-zinc-50 px-3 py-3 dark:bg-zinc-900">
                <p className="text-xl font-bold text-red-500">{failed}</p>
                <p className="text-xs text-zinc-500">Failed</p>
              </div>
              <div className="rounded-2xl bg-zinc-50 px-3 py-3 dark:bg-zinc-900">
                <p className="text-xl font-bold text-zinc-900 dark:text-white">
                  {submitted + failed}
                </p>
                <p className="text-xs text-zinc-500">Touched</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
