// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  listSessions,
  getApplicationLog,
  type SessionListItem,
  type ApplicationLogEntry,
  API_BASE,
} from "@/lib/api";
import { downloadResumePdf, downloadCoverLetterPdf } from "@/lib/pdf";

type Tab = "all" | "submitted" | "failed" | "skipped";

const STATUS_COLORS: Record<string, string> = {
  submitted: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  failed: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  skipped: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

type EnrichedEntry = ApplicationLogEntry & {
  sessionId: string;
  sessionKeywords: string[];
};

export default function ApplyPage() {
  const [entries, setEntries] = useState<EnrichedEntry[]>([]);
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("all");
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [expandedScreenshot, setExpandedScreenshot] = useState<string | null>(null);

  const fetchAll = async () => {
    try {
      const allSessions = await listSessions();
      setSessions(allSessions);

      const allEntries: EnrichedEntry[] = [];
      await Promise.all(
        allSessions.map(async (session) => {
          try {
            const log = await getApplicationLog(session.session_id);
            for (const entry of log.entries) {
              allEntries.push({
                ...entry,
                sessionId: session.session_id,
                sessionKeywords: session.keywords,
              });
            }
          } catch {
            // skip sessions with no log
          }
        })
      );

      setEntries(allEntries);
    } catch {
      setEntries([]);
      setSessions([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, []);

  // Auto-refresh every 15 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchAll();
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  const filtered = tab === "all" ? entries : entries.filter((e) => e.status === tab);

  const counts = {
    all: entries.length,
    submitted: entries.filter((e) => e.status === "submitted").length,
    failed: entries.filter((e) => e.status === "failed").length,
    skipped: entries.filter((e) => e.status === "skipped").length,
  };

  const readyToApplyCount = counts.failed + counts.skipped;

  const copyToClipboard = (text: string, fieldId: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(fieldId);
    setTimeout(() => setCopiedField(null), 2000);
  };

  return (
    <div className="flex-1 max-w-5xl mx-auto w-full px-6 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Review & Apply</h1>
        <p className="text-muted-foreground mt-1">
          All your applications in one place. Download tailored resumes and cover letters, or finish
          applications that need your attention.
        </p>
      </div>

      {/* Stat cards */}
      <div className="mb-6 grid gap-3 md:grid-cols-3">
        <Card className="border-emerald-200 dark:border-emerald-900">
          <CardContent className="p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
              Total Applications
            </p>
            <p className="mt-1 text-2xl font-bold text-emerald-600 dark:text-emerald-400">
              {counts.all}
            </p>
          </CardContent>
        </Card>
        <Card className="border-amber-200 dark:border-amber-900">
          <CardContent className="p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
              Ready to Apply
            </p>
            <p className="mt-1 text-2xl font-bold text-amber-600 dark:text-amber-400">
              {readyToApplyCount}
            </p>
          </CardContent>
        </Card>
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Card className="border-blue-200 dark:border-blue-900 cursor-pointer transition-colors hover:bg-muted/40">
                <CardContent className="p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                    Sessions
                  </p>
                  <p className="mt-1 text-2xl font-bold text-blue-600 dark:text-blue-400">
                    {sessions.length}
                  </p>
                </CardContent>
              </Card>
            </TooltipTrigger>
            <TooltipContent
              side="bottom"
              className="bg-popover text-popover-foreground border border-border shadow-lg p-0 rounded-xl"
            >
              {sessions.length === 0 ? (
                <p className="px-3 py-2 text-xs text-muted-foreground">No sessions yet</p>
              ) : (
                <div className="py-1">
                  <p className="px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-muted-foreground font-medium">
                    Recent Sessions
                  </p>
                  {sessions.slice(0, 5).map((s) => (
                    <Link
                      key={s.session_id}
                      href={`/session/${s.session_id}`}
                      className="flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-muted/60 transition-colors"
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full shrink-0 ${
                          s.status === "running"
                            ? "bg-emerald-500"
                            : s.status === "paused"
                            ? "bg-amber-500"
                            : "bg-zinc-400"
                        }`}
                      />
                      <span className="truncate max-w-[180px]">
                        {s.keywords.length > 0 ? s.keywords.join(", ") : s.session_id.slice(0, 8)}
                      </span>
                    </Link>
                  ))}
                </div>
              )}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {(["all", "submitted", "failed", "skipped"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              tab === t
                ? "bg-primary text-primary-foreground"
                : "bg-muted/50 text-muted-foreground hover:bg-muted"
            }`}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)} ({counts[t]})
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-muted rounded-xl animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <p className="text-lg font-medium text-muted-foreground">No applications yet</p>
            <p className="text-sm text-muted-foreground/70 mt-1">
              Start a session to begin your job search.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {filtered.map((entry, idx) => {
            const key = `${entry.sessionId}-${entry.job?.id || idx}`;
            const company = entry.job?.company || "Company";
            const title = entry.job?.title || "Position";
            return (
              <Card key={key} className="overflow-hidden">
                <CardContent className="py-4">
                  {/* Header row */}
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge className={`text-xs ${STATUS_COLORS[entry.status]}`}>
                          {entry.status}
                        </Badge>
                        {entry.error?.startsWith("duplicate:") && (
                          <Badge className="text-xs bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                            Previously Applied
                          </Badge>
                        )}
                        <span className="text-sm font-semibold truncate">{title}</span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {company}
                        {entry.job?.location ? ` · ${entry.job.location}` : ""}
                        {entry.job?.board ? (
                          <Badge variant="outline" className="ml-2 text-[10px] py-0">
                            {entry.job.board}
                          </Badge>
                        ) : null}
                      </p>
                      {/* Session keywords */}
                      {entry.sessionKeywords.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {entry.sessionKeywords.map((kw) => (
                            <Badge key={kw} variant="secondary" className="text-[10px] py-0 px-1.5">
                              {kw}
                            </Badge>
                          ))}
                        </div>
                      )}
                      {entry.error && (
                        <p className="text-xs text-red-500 mt-1 truncate">{entry.error}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {entry.job?.url && (
                        <a href={entry.job.url} target="_blank" rel="noopener noreferrer">
                          <Button size="sm" variant="outline" className="gap-1 text-xs">
                            <svg
                              className="w-3 h-3"
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
                            Apply
                          </Button>
                        </a>
                      )}
                    </div>
                  </div>

                  {/* Artifact action buttons */}
                  {(entry.cover_letter || entry.tailored_resume) && (
                    <div className="flex flex-wrap items-center gap-2 mt-3 pt-3 border-t border-border/50">
                      {entry.cover_letter && (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs gap-1.5"
                            onClick={() =>
                              downloadCoverLetterPdf(
                                entry.cover_letter,
                                company,
                                title,
                                `Cover Letter - ${company} - ${title}`
                              )
                            }
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
                                d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                              />
                            </svg>
                            Cover Letter PDF
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs"
                            onClick={() => copyToClipboard(entry.cover_letter, `cover-${key}`)}
                          >
                            {copiedField === `cover-${key}` ? "Copied!" : "Copy Cover Letter"}
                          </Button>
                        </>
                      )}
                      {entry.tailored_resume && (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs gap-1.5"
                            onClick={() =>
                              downloadResumePdf(
                                entry.tailored_resume!.tailored_text,
                                `Resume - ${company} - ${title}`
                              )
                            }
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
                                d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                              />
                            </svg>
                            Resume PDF
                            {entry.tailored_resume.fit_score > 0 && (
                              <Badge variant="secondary" className="ml-1 text-[10px] py-0">
                                {entry.tailored_resume.fit_score}% fit
                              </Badge>
                            )}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs"
                            onClick={() =>
                              copyToClipboard(entry.tailored_resume!.tailored_text, `resume-${key}`)
                            }
                          >
                            {copiedField === `resume-${key}` ? "Copied!" : "Copy Resume"}
                          </Button>
                        </>
                      )}
                    </div>
                  )}

                  {/* Confirmation screenshot */}
                  {entry.screenshot_path && (
                    <div className="mt-3 pt-3 border-t border-border/50">
                      <button
                        type="button"
                        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                        onClick={() =>
                          setExpandedScreenshot(expandedScreenshot === key ? null : key)
                        }
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
                            d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0022.5 18.75V5.25A2.25 2.25 0 0020.25 3H3.75A2.25 2.25 0 001.5 5.25v13.5A2.25 2.25 0 003.75 21z"
                          />
                        </svg>
                        {expandedScreenshot === key
                          ? "Hide confirmation screenshot"
                          : "View confirmation screenshot"}
                      </button>
                      {expandedScreenshot === key && (
                        <div className="mt-2 rounded-lg border border-border overflow-hidden">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={`${API_BASE}/api/sessions/${
                              entry.sessionId
                            }/screenshot?path=${encodeURIComponent(entry.screenshot_path)}`}
                            alt="Confirmation screenshot"
                            className="w-full"
                          />
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
