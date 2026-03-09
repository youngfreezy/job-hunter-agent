// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  listSessions,
  getApplicationLog,
  type SessionListItem,
  type ApplicationLogEntry,
} from "@/lib/api";

// Industry average: finding a listing, writing custom cover letter & resume, filling forms, submitting
const MANUAL_MINUTES_PER_APP = 60;

type SessionWithApps = {
  session: SessionListItem;
  entries: ApplicationLogEntry[];
  timeSaved: number;
  automationTime: number;
  manualEstimate: number;
};

const STATUS_LABELS: Record<string, string> = {
  intake: "Starting",
  coaching: "Coaching",
  discovering: "Discovering",
  scoring: "Scoring",
  tailoring: "Tailoring",
  applying: "Applying",
  awaiting_coach_review: "Resume Review",
  awaiting_review: "Shortlist Review",
  needs_intervention: "Needs Help",
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

const APP_STATUS_COLORS: Record<string, string> = {
  submitted: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  failed: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  skipped: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

function formatTime(minutes: number): string {
  if (minutes < 0) return "0 min";
  if (minutes >= 60) {
    const hrs = Math.floor(minutes / 60);
    const mins = Math.round(minutes % 60);
    return mins > 0 ? `${hrs} hrs ${mins} min` : `${hrs} hrs`;
  }
  return `${Math.round(minutes)} min`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function computeTimeSaved(entries: ApplicationLogEntry[]): {
  timeSaved: number;
  automationTime: number;
  manualEstimate: number;
} {
  const totalApps = entries.length;
  const manualEstimate = totalApps * MANUAL_MINUTES_PER_APP;

  const hasDurationData = entries.some((e) => e.duration != null);
  let automationTime: number;

  if (hasDurationData) {
    automationTime = entries.reduce((sum, e) => {
      if (e.duration != null) {
        return sum + e.duration / 60; // seconds to minutes
      }
      return sum + 2; // fallback for entries without duration
    }, 0);
  } else {
    automationTime = totalApps * 2; // estimate 2 min per app
  }

  const timeSaved = manualEstimate - automationTime;
  return { timeSaved: Math.max(0, timeSaved), automationTime, manualEstimate };
}

export default function HistoryPage() {
  const [sessionsWithApps, setSessionsWithApps] = useState<SessionWithApps[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchAll = async () => {
    try {
      const allSessions = await listSessions();
      // Fetch application logs sequentially (3 at a time) to avoid 429 rate limits
      const results: SessionWithApps[] = [];
      const BATCH_SIZE = 3;
      for (let i = 0; i < allSessions.length; i += BATCH_SIZE) {
        const batch = allSessions.slice(i, i + BATCH_SIZE);
        const batchResults = await Promise.all(
          batch.map(async (session) => {
            let entries: ApplicationLogEntry[] = [];
            try {
              const log = await getApplicationLog(session.session_id);
              entries = log.entries;
            } catch {
              // session may not have an application log yet
            }
            const { timeSaved, automationTime, manualEstimate } = computeTimeSaved(entries);
            return { session, entries, timeSaved, automationTime, manualEstimate };
          })
        );
        results.push(...batchResults);
      }

      // Sort by most recent first
      results.sort(
        (a, b) =>
          new Date(b.session.created_at).getTime() - new Date(a.session.created_at).getTime()
      );

      setSessionsWithApps(results);
    } catch {
      setSessionsWithApps([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, []);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchAll();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const totals = useMemo(() => {
    const totalTimeSaved = sessionsWithApps.reduce((sum, s) => sum + s.timeSaved, 0);
    const totalApps = sessionsWithApps.reduce((sum, s) => sum + s.entries.length, 0);
    const avgSavedPerApp = totalApps > 0 ? totalTimeSaved / totalApps : 0;
    return {
      timeSaved: totalTimeSaved,
      sessions: sessionsWithApps.length,
      applications: totalApps,
      avgPerApp: avgSavedPerApp,
    };
  }, [sessionsWithApps]);

  return (
    <div className="flex-1 max-w-5xl mx-auto w-full px-6 py-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Your Search History</h1>
        <p className="text-muted-foreground mt-1">
          See how much time you&apos;ve saved and track every session from start to finish.
        </p>
      </div>

      {loading ? (
        <div className="space-y-6">
          <div className="h-36 bg-muted rounded-2xl animate-pulse" />
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-24 bg-muted rounded-2xl animate-pulse" />
            ))}
          </div>
        </div>
      ) : sessionsWithApps.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <p className="text-lg font-medium text-muted-foreground">
              No sessions yet. Start your first search and we&apos;ll track your progress here.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Time Saved Hero Card */}
          <Card className="mb-6 overflow-hidden rounded-2xl border-0 bg-gradient-to-r from-blue-50 to-emerald-50 dark:from-blue-950/30 dark:to-emerald-950/30">
            <CardContent className="p-6">
              <div className="text-center mb-4">
                <p className="text-4xl font-bold text-emerald-600 dark:text-emerald-400">
                  {formatTime(totals.timeSaved)}
                </p>
                <p className="text-sm font-medium text-muted-foreground mt-1">Total time saved</p>
              </div>
              <div className="flex items-center justify-center gap-6 text-sm text-muted-foreground">
                <span>
                  <span className="font-semibold text-foreground">{totals.sessions}</span> sessions
                  completed
                </span>
                <span className="text-border">|</span>
                <span>
                  <span className="font-semibold text-foreground">{totals.applications}</span> total
                  applications
                </span>
                <span className="text-border">|</span>
                <span>
                  ~
                  <span className="font-semibold text-foreground">
                    {Math.round(totals.avgPerApp)} min
                  </span>{" "}
                  saved per application
                </span>
              </div>
              <p className="text-xs text-muted-foreground/70 text-center mt-4">
                Based on data from{" "}
                <a
                  href="https://www.hrdive.com/news/job-application-process-should-take-less-than-30-minutes/747352/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-muted-foreground"
                >
                  HR Dive
                </a>{" "}
                and the{" "}
                <a
                  href="https://www.bls.gov/opub/btn/volume-9/how-do-jobseekers-search-for-jobs.htm"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-muted-foreground"
                >
                  U.S. Bureau of Labor Statistics
                </a>
                , we estimate each manual application takes about an hour including research,
                writing a custom resume and cover letter, and form filling. Your actual time saved
                is based on real session data.
              </p>
            </CardContent>
          </Card>

          {/* Session List */}
          <div className="space-y-3">
            {sessionsWithApps.map(
              ({ session, entries, timeSaved, automationTime, manualEstimate }) => {
                const isExpanded = expandedId === session.session_id;
                const submittedCount = entries.filter((e) => e.status === "submitted").length;

                return (
                  <Card
                    key={session.session_id}
                    className={`overflow-hidden rounded-2xl transition-colors ${
                      isExpanded ? "bg-zinc-50 dark:bg-zinc-900/30" : ""
                    }`}
                  >
                    <CardContent className="p-0">
                      {/* Collapsed view - clickable header */}
                      <button
                        type="button"
                        className="w-full text-left px-5 py-4"
                        onClick={() => setExpandedId(isExpanded ? null : session.session_id)}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <Badge variant={STATUS_COLORS[session.status] || "outline"}>
                                {STATUS_LABELS[session.status] || session.status}
                              </Badge>
                              <span className="text-sm font-semibold truncate">
                                {session.keywords.join(", ") || "Untitled"}
                              </span>
                              {session.remote_only && (
                                <Badge variant="secondary" className="text-[10px] py-0">
                                  Remote
                                </Badge>
                              )}
                            </div>
                            {session.locations.length > 0 && (
                              <p className="text-xs text-muted-foreground mt-0.5">
                                {session.locations.join(", ")}
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-4 shrink-0 text-xs text-muted-foreground">
                            <span>
                              <span className="font-semibold text-foreground">
                                {submittedCount}
                              </span>{" "}
                              applied
                            </span>
                            <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                              {formatTime(timeSaved)} saved
                            </span>
                            <span>{formatDate(session.created_at)}</span>
                            <svg
                              className={`w-4 h-4 transition-transform ${
                                isExpanded ? "rotate-180" : ""
                              }`}
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                              strokeWidth={2}
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M19 9l-7 7-7-7"
                              />
                            </svg>
                          </div>
                        </div>
                      </button>

                      {/* Expanded view */}
                      {isExpanded && (
                        <div className="px-5 pb-5 border-t border-border/50">
                          {/* Time metrics card */}
                          <div className="mt-4 rounded-xl bg-emerald-50 dark:bg-emerald-950/20 p-4">
                            <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">
                              This session saved you {formatTime(timeSaved)}
                            </p>
                            <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
                              <span>
                                Manual estimate:{" "}
                                <span className="font-medium text-foreground">
                                  {formatTime(manualEstimate)}
                                </span>
                              </span>
                              <span className="text-border">|</span>
                              <span>
                                Automation time:{" "}
                                <span className="font-medium text-foreground">
                                  {formatTime(automationTime)}
                                </span>
                              </span>
                              <span className="text-border">|</span>
                              <span>
                                You saved:{" "}
                                <span className="font-medium text-emerald-600 dark:text-emerald-400">
                                  {formatTime(timeSaved)}
                                </span>
                              </span>
                            </div>
                          </div>

                          {/* Application entries */}
                          {entries.length > 0 ? (
                            <div className="mt-4 space-y-2">
                              {entries.map((entry, idx) => (
                                <div
                                  key={`${entry.job?.id || idx}`}
                                  className="flex items-center gap-3 rounded-lg border border-border/50 px-3 py-2.5 text-sm"
                                >
                                  <Badge
                                    className={`text-xs shrink-0 ${
                                      APP_STATUS_COLORS[entry.status] || ""
                                    }`}
                                  >
                                    {entry.status}
                                  </Badge>
                                  <div className="min-w-0 flex-1">
                                    <span className="font-medium truncate block">
                                      {entry.job?.title || "Position"}
                                    </span>
                                    <span className="text-xs text-muted-foreground">
                                      {entry.job?.company || "Company"}
                                    </span>
                                  </div>
                                  {entry.job?.board && (
                                    <Badge variant="outline" className="text-[10px] py-0 shrink-0">
                                      {entry.job.board}
                                    </Badge>
                                  )}
                                  {entry.duration != null && (
                                    <span className="text-xs text-muted-foreground shrink-0">
                                      {Math.round(entry.duration)}s
                                    </span>
                                  )}
                                  {entry.job?.url && (
                                    <a
                                      href={entry.job.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      onClick={(e) => e.stopPropagation()}
                                      className="text-blue-600 hover:text-blue-700 dark:text-blue-400 shrink-0"
                                    >
                                      <svg
                                        className="w-3.5 h-3.5"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                        strokeWidth={2}
                                      >
                                        <path
                                          strokeLinecap="round"
                                          strokeLinejoin="round"
                                          d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
                                        />
                                      </svg>
                                    </a>
                                  )}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="mt-4 text-sm text-muted-foreground">
                              No applications recorded for this session yet.
                            </p>
                          )}

                          {/* Action buttons */}
                          <div className="flex gap-2 mt-4">
                            <Link href={`/session/${session.session_id}`}>
                              <Button size="sm" variant="outline">
                                View Full Details
                              </Button>
                            </Link>
                            <Link href={`/session/${session.session_id}/manual-apply`}>
                              <Button size="sm" variant="outline">
                                Review Applications
                              </Button>
                            </Link>
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              }
            )}
          </div>
        </>
      )}
    </div>
  );
}
