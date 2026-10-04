// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getApplicationLog, type ApplicationLogEntry } from "@/lib/api";
import { SessionScreenshot } from "@/components/SessionScreenshot";
import { downloadResumePdf, downloadCoverLetterPdf } from "@/lib/pdf";

type Tab = "all" | "failed" | "skipped" | "submitted";

const STATUS_COLORS: Record<string, string> = {
  submitted: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  failed: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  skipped: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

export default function ManualApplyPage() {
  const { id: sessionId } = useParams<{ id: string }>();
  const [entries, setEntries] = useState<ApplicationLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("all");
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [expandedScreenshot, setExpandedScreenshot] = useState<string | null>(null);

  useEffect(() => {
    getApplicationLog(sessionId)
      .then((data) => setEntries(data.entries))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, [sessionId]);

  // Auto-refresh every 10s while session is active
  useEffect(() => {
    const interval = setInterval(() => {
      getApplicationLog(sessionId)
        .then((data) => setEntries(data.entries))
        .catch(() => {});
    }, 10000);
    return () => clearInterval(interval);
  }, [sessionId]);

  const filtered = tab === "all" ? entries : entries.filter((e) => e.status === tab);

  const counts = {
    all: entries.length,
    submitted: entries.filter((e) => e.status === "submitted").length,
    failed: entries.filter((e) => e.status === "failed").length,
    skipped: entries.filter((e) => e.status === "skipped").length,
  };

  const copyToClipboard = (text: string, fieldId: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(fieldId);
    setTimeout(() => setCopiedField(null), 2000);
  };

  return (
    <div className="w-full">
      <p className="mb-4 text-sm text-muted-foreground">
        Every application from this run. Download the tailored materials or finish an application
        yourself.
      </p>

      <dl className="mb-6 grid gap-x-6 gap-y-2 rounded-xl border border-border bg-card p-4 text-sm sm:grid-cols-[8rem_1fr]">
        <dt className="font-medium">Submitted</dt>
        <dd className="text-muted-foreground">
          Sent to the employer. Open one to see the exact resume and cover letter. 1 credit.
        </dd>
        <dt className="font-medium">Failed</dt>
        <dd className="text-muted-foreground">
          Materials were written but the form could not be sent. Use them to apply yourself. 0.5
          credits.
        </dd>
        <dt className="font-medium">Skipped</dt>
        <dd className="text-muted-foreground">
          Dropped before any work, for example already applied or a duplicate. No charge.
        </dd>
      </dl>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {(["all", "failed", "skipped", "submitted"] as Tab[]).map((t) => (
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
              Applications will appear here as your search progresses. This is your go-to place for
              tracking and following up.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {filtered.map((entry, idx) => {
            const key = entry.job?.id || `entry-${idx}`;
            const company = entry.job?.company || "Company";
            const title = entry.job?.title || "Position";
            return (
              <Card key={key} className="overflow-hidden">
                <CardContent className="py-4">
                  {/* Header row */}
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
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

                  {/* Artifact action buttons – always visible */}
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
                          ? "Hide application screenshot"
                          : "View application screenshot"}
                      </button>
                      {expandedScreenshot === key && (
                        <div className="mt-2 rounded-lg border border-border overflow-hidden">
                          <SessionScreenshot sessionId={sessionId} path={entry.screenshot_path} alt="Application screenshot" />
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
