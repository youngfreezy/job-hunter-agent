// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
  listSessions,
  getLifetimeStats,
  rerunSession,
  type SessionListItem,
  type LifetimeStats,
} from "@/lib/api";
import ApplicationsTimeline from "@/components/charts/ApplicationsTimeline";

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

const STATUS_COLORS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
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

function formatRelativeDate(value: string | null | undefined) {
  if (!value) return "";
  const date = new Date(value);
  if (isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function getSessionHeadline(session: SessionListItem) {
  if (session.status === "awaiting_coach_review") {
    return "Your improved resume is ready for review";
  }
  if (session.status === "awaiting_review") {
    return "Your matched jobs are ready for review";
  }
  if (session.status === "needs_intervention") {
    return "A site needs your help to continue";
  }
  if (session.status === "paused") {
    return "Search paused — resume whenever you're ready";
  }
  if (session.status === "completed") {
    return "Search complete — review your results";
  }
  if (session.status === "failed") {
    return "Something went wrong — check the details to retry";
  }
  return "Your search is running — check in anytime for live updates";
}

function formatTimeSaved(minutes: number): { value: string; unit: string; subtitle: string } {
  const hours = minutes / 60;
  if (hours >= 1) {
    const h = Math.round(hours * 10) / 10;
    const workDays = Math.round((hours / 8) * 10) / 10;
    return {
      value: h % 1 === 0 ? h.toFixed(0) : h.toFixed(1),
      unit: h === 1 ? "hour" : "hours",
      subtitle:
        workDays >= 1
          ? `That\u2019s ${workDays >= 2 ? workDays.toFixed(0) : workDays.toFixed(1)} work ${
              workDays === 1 ? "day" : "days"
            } you got back`
          : `${Math.round(minutes)} minutes of manual work saved`,
    };
  }
  return {
    value: Math.round(minutes).toString(),
    unit: "min",
    subtitle: "of manual work saved",
  };
}

export default function Dashboard() {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [stats, setStats] = useState<LifetimeStats | null>(null);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchSessions = useCallback(() => {
    listSessions()
      .then(setSessions)
      .catch((err) => console.error("Failed to load sessions:", err))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    getLifetimeStats()
      .then(setStats)
      .catch((err) => console.error("Failed to load lifetime stats:", err));
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // Auto-refresh every 15s when there are active sessions
  const hasActive = sessions.some((s) => !["completed", "failed"].includes(s.status));
  useEffect(() => {
    if (!hasActive) {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
      return;
    }
    pollRef.current = setInterval(fetchSessions, 15000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [hasActive, fetchSessions]);

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
      !ACTION_REQUIRED.has(session.status) && !["completed", "failed"].includes(session.status)
  );
  const completedSessions = sortedSessions.filter((session) =>
    ["completed", "failed"].includes(session.status)
  );


  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr] items-start">
        <Card className="border-zinc-200 dark:border-zinc-800 h-[480px] flex flex-col overflow-hidden">
          <CardContent className="flex flex-col gap-5 p-8 overflow-y-auto min-h-0">
            <div>
              <p className="text-sm font-medium uppercase tracking-[0.22em] text-zinc-500">
                Dashboard
              </p>
              {stats && stats.total_submitted > 0 ? (
                (() => {
                  const ts = formatTimeSaved(stats.time_saved_minutes);
                  return (
                    <>
                      <h1 className="mt-2 text-4xl font-bold tracking-tight">
                        <span className="text-emerald-600 dark:text-emerald-400">
                          {ts.value} {ts.unit}
                        </span>{" "}
                        saved
                      </h1>
                      <p className="mt-1 text-zinc-600 dark:text-zinc-400">{ts.subtitle}</p>
                      <p className="mt-1 text-sm text-zinc-500">
                        {stats.total_submitted} applications sent across {stats.total_sessions}{" "}
                        {stats.total_sessions === 1 ? "session" : "sessions"}
                      </p>
                    </>
                  );
                })()
              ) : (
                <>
                  <h1 className="mt-2 text-4xl font-bold tracking-tight">
                    Your Job Search at a Glance
                  </h1>
                  <p className="mt-3 max-w-2xl text-zinc-600 dark:text-zinc-400">
                    Sessions that need your attention come first. See what&apos;s active,
                    what&apos;s done, and what needs you — all in one view.
                  </p>
                </>
              )}
              <Link href="/session/new" className="inline-block mt-4">
                <Button size="lg">Start New Session</Button>
              </Link>
            </div>
            <div className="grid gap-3 sm:grid-cols-4">
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/30">
                <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
                  Needs Attention
                </p>
                <p className="mt-2 text-3xl font-bold text-amber-900 dark:text-amber-100">
                  {actionRequiredSessions.length}
                </p>
                <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
                  Waiting for your decision
                </p>
              </div>
              <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950/30">
                <p className="text-sm font-medium text-blue-800 dark:text-blue-300">In Progress</p>
                <p className="mt-2 text-3xl font-bold text-blue-900 dark:text-blue-100">
                  {activeSessions.length}
                </p>
                <p className="mt-1 text-xs text-blue-700 dark:text-blue-400">
                  {hasActive && (
                    <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse mr-1" />
                  )}
                  Actively running
                </p>
              </div>
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-900 dark:bg-emerald-950/30">
                <p className="text-sm font-medium text-emerald-800 dark:text-emerald-300">
                  Apps Sent
                </p>
                <p className="mt-2 text-3xl font-bold text-emerald-900 dark:text-emerald-100">
                  {sessions.reduce((sum, s) => sum + s.applications_submitted, 0)}
                </p>
                <p className="mt-1 text-xs text-emerald-700 dark:text-emerald-400">
                  Total submitted
                </p>
              </div>
              <div className="rounded-2xl border border-violet-200 bg-violet-50 p-4 dark:border-violet-900 dark:bg-violet-950/30">
                <p className="text-sm font-medium text-violet-800 dark:text-violet-300">
                  Success Rate
                </p>
                <p className="mt-2 text-3xl font-bold text-violet-900 dark:text-violet-100">
                  {(() => {
                    const total = sessions.reduce(
                      (sum, s) => sum + s.applications_submitted + s.applications_failed,
                      0
                    );
                    if (total === 0) return "—";
                    const rate = Math.round(
                      (sessions.reduce((sum, s) => sum + s.applications_submitted, 0) / total) * 100
                    );
                    return `${rate}%`;
                  })()}
                </p>
                <p className="mt-1 text-xs text-violet-700 dark:text-violet-400">
                  Submitted / attempted
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-zinc-200 dark:border-zinc-800 h-[480px] flex flex-col overflow-hidden">
          <CardHeader className="shrink-0">
            <CardTitle className="text-lg">Needs Your Attention</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 overflow-y-auto min-h-0">
            {loading ? (
              [1, 2, 3].map((item) => (
                <div
                  key={item}
                  className="h-16 rounded-2xl bg-zinc-100 animate-pulse dark:bg-zinc-900"
                />
              ))
            ) : actionRequiredSessions.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-zinc-300 p-5 text-sm text-zinc-500 dark:border-zinc-700">
                You&apos;re all caught up. Start a new search or check your active sessions.
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
                      <Badge variant={STATUS_COLORS[session.status] || "secondary"}>
                        {STATUS_LABELS[session.status] || session.status}
                      </Badge>
                      <p className="mt-2 font-medium">{(session.keywords || []).join(", ")}</p>
                      <p className="mt-1 text-sm text-zinc-500">{getSessionHeadline(session)}</p>
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

      {!loading && sessions.length === 0 ? (
        <div className="mt-10">
          <Card className="border-dashed">
            <CardContent className="py-16 text-center">
              <p className="text-xl font-semibold">Ready to start your job search?</p>
              <p className="mt-2 text-sm text-zinc-500 max-w-md mx-auto">
                Create your first session to search job boards, get your resume optimized, and start
                applying automatically.
              </p>
              <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
                <Link href="/session/new">
                  <Button size="lg">Start New Session</Button>
                </Link>
                <Link href="/career-pivot">
                  <Button size="lg" variant="outline">
                    Check Your AI Risk
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : (
        <div className="mt-10 space-y-10">
          {activeSessions.length > 0 && (
            <section>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-semibold">Active Sessions</h2>
                  <p className="text-sm text-zinc-500">
                    Your searches that are actively finding and applying to jobs.
                  </p>
                </div>
              </div>
              <div className="space-y-3">
                {activeSessions.map((session) => (
                  <SessionCard key={session.session_id} session={session} />
                ))}
              </div>
            </section>
          )}

          <ApplicationsTimeline sessions={completedSessions} />

          {completedSessions.length > 0 && (
            <section>
              <div className="mb-4">
                <h2 className="text-xl font-semibold">Past Searches</h2>
                <p className="text-sm text-zinc-500">
                  Review results from completed searches or retry ones that ran into issues.
                </p>
              </div>
              <div className="space-y-3">
                {completedSessions.map((session) => (
                  <SessionCard
                    key={session.session_id}
                    session={session}
                    onSessionLaunched={fetchSessions}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* Autopilot Mode CTA */}
      <div className="mt-10">
        <Card className="border-dashed border-indigo-200 bg-gradient-to-br from-indigo-50/50 to-violet-50/50 dark:border-indigo-800 dark:from-indigo-950/30 dark:to-violet-950/30">
          <CardContent className="py-8 text-center">
            <p className="text-xl font-semibold">Autopilot Mode</p>
            <p className="mt-2 text-sm text-zinc-500 max-w-lg mx-auto">
              Set up automated job searches on a schedule — daily or weekly with an approval gate
              before any applications go out. You stay in control, we do the work.
            </p>
            <Link href="/autopilot" className="inline-block mt-4">
              <Button variant="outline" className="border-indigo-300 text-indigo-600 hover:bg-indigo-50 dark:border-indigo-700 dark:text-indigo-400 dark:hover:bg-indigo-950">
                Manage Schedules
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function SessionCard({
  session,
  onSessionLaunched,
}: {
  session: SessionListItem;
  onSessionLaunched?: () => void;
}) {
  const submitted = session.applications_submitted;
  const failed = session.applications_failed;
  const total = submitted + failed;
  const successRate = total > 0 ? Math.round((submitted / total) * 100) : null;
  const isRunning =
    !["completed", "failed"].includes(session.status) && !ACTION_REQUIRED.has(session.status);
  const isDone = ["completed", "failed"].includes(session.status);

  const [editing, setEditing] = useState(false);
  const [editKeywords, setEditKeywords] = useState((session.keywords || []).join(", "));
  const [editLocations, setEditLocations] = useState((session.locations || []).join(", "));
  const [editSalary, setEditSalary] = useState(session.salary_min?.toString() || "");
  const [editRemote, setEditRemote] = useState(session.remote_only);
  const [launched, setLaunched] = useState(false);

  const handleRerun = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setLaunched(true);
    try {
      await rerunSession(session.session_id);
      toast.success("Session started");
      onSessionLaunched?.();
    } catch (err) {
      setLaunched(false);
      toast.error(err instanceof Error ? err.message : "Failed to re-run");
    }
  };

  const handleEditRun = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const keywords = editKeywords
      .split(",")
      .map((k) => k.trim())
      .filter(Boolean);
    const locations = editRemote
      ? []
      : editLocations
          .split(",")
          .map((l) => l.trim())
          .filter(Boolean);
    if (keywords.length === 0) {
      toast.error("Enter at least one keyword");
      return;
    }
    setLaunched(true);
    try {
      await rerunSession(session.session_id, {
        keywords,
        locations,
        remote_only: editRemote,
        salary_min: editSalary ? parseInt(editSalary) : null,
      });
      setEditing(false);
      toast.success("Session started with updated params");
      onSessionLaunched?.();
    } catch (err) {
      setLaunched(false);
      toast.error(err instanceof Error ? err.message : "Failed to start");
    }
  };

  return (
    <Card className="border-zinc-200 transition-colors hover:border-zinc-400 dark:border-zinc-800 dark:hover:border-zinc-600">
      <CardContent className="py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <Link href={`/session/${session.session_id}`} className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={STATUS_COLORS[session.status] || "secondary"}>
                {isRunning && (
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-current mr-1.5 animate-pulse" />
                )}
                {STATUS_LABELS[session.status] || session.status}
              </Badge>
              <span className="text-sm text-zinc-500">
                {formatRelativeDate(session.created_at)}
              </span>
              {session.remote_only && <Badge variant="outline">Remote only</Badge>}
            </div>
            <p className="mt-3 text-lg font-semibold">{(session.keywords || []).join(", ")}</p>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {getSessionHeadline(session)}
            </p>
            {(session.locations || []).length > 0 && (
              <p className="mt-2 text-sm text-zinc-500">
                Targeting {(session.locations || []).join(", ")}
              </p>
            )}
            {session.salary_min && (
              <p className="mt-1 text-sm text-zinc-500">
                Min ${session.salary_min.toLocaleString()}
              </p>
            )}
          </Link>
          <div className="min-w-[220px]">
            <div className="grid grid-cols-3 gap-2 text-center">
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
                  {successRate !== null ? `${successRate}%` : "—"}
                </p>
                <p className="text-xs text-zinc-500">Success</p>
              </div>
            </div>
            {isRunning && (
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-blue-500 to-blue-600 animate-progress-pulse"
                  style={{ width: "60%" }}
                />
              </div>
            )}
            {isDone && (
              <div className="mt-3">
                {launched && (
                  <div className="mb-2 flex items-center justify-center gap-1.5 rounded-full bg-blue-50 py-1 text-xs font-medium text-blue-600 dark:bg-blue-950/40 dark:text-blue-400">
                    <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                    Running
                  </div>
                )}
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={launched}
                    onClick={handleRerun}
                    className="flex-1"
                  >
                    {launched ? "Running..." : "Re-run"}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={launched}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setEditing(!editing);
                    }}
                    className="flex-1"
                  >
                    {editing ? "Cancel" : "Edit & Run"}
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Inline edit panel */}
        {editing && (
          <div
            className="mt-4 border-t border-zinc-200 pt-4 dark:border-zinc-800"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-medium text-zinc-500">Keywords</label>
                <input
                  type="text"
                  value={editKeywords}
                  onChange={(e) => setEditKeywords(e.target.value)}
                  className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                  placeholder="AI Engineer, React"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-zinc-500">Locations</label>
                <input
                  type="text"
                  value={editLocations}
                  onChange={(e) => setEditLocations(e.target.value)}
                  disabled={editRemote}
                  className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900"
                  placeholder="San Francisco, Remote"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-zinc-500">Min Salary</label>
                <input
                  type="number"
                  value={editSalary}
                  onChange={(e) => setEditSalary(e.target.value)}
                  className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                  placeholder="150000"
                />
              </div>
              <div className="flex items-end gap-3 pb-1">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={editRemote}
                    onChange={(e) => setEditRemote(e.target.checked)}
                    className="rounded"
                  />
                  Remote only
                </label>
              </div>
            </div>
            <div className="mt-3 flex justify-end">
              <Button size="sm" disabled={launched} onClick={handleEditRun}>
                {launched ? "Running..." : "Run with Changes"}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
