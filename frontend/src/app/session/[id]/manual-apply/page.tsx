"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getSkippedJobs, type SkippedJob } from "@/lib/api";

export default function ManualApplyPage() {
  const { id: sessionId } = useParams<{ id: string }>();
  const [jobs, setJobs] = useState<SkippedJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  useEffect(() => {
    getSkippedJobs(sessionId)
      .then((data) => setJobs(data.skipped_jobs))
      .catch(() => setJobs([]))
      .finally(() => setLoading(false));
  }, [sessionId]);

  const copyToClipboard = (text: string, fieldId: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(fieldId);
    setTimeout(() => setCopiedField(null), 2000);
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Navbar */}
      <nav className="sticky top-0 z-50 backdrop-blur-xl bg-background/80 border-b border-border/50 px-6 py-3">
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
              className="px-3 py-1.5 text-sm font-medium rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
            >
              Activity
            </Link>
            <Link
              href={`/session/${sessionId}/manual-apply`}
              className="px-3 py-1.5 text-sm font-medium rounded-md bg-primary/10 text-primary"
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
          <Link href="/dashboard">
            <Button variant="outline" size="sm">
              Dashboard
            </Button>
          </Link>
        </div>
      </nav>

      {/* Content */}
      <div className="flex-1 max-w-5xl mx-auto w-full px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold">Manual Apply</h1>
          <p className="text-muted-foreground mt-1">
            These jobs require authentication to apply. Use the links below to apply directly with your tailored resume and cover letter.
          </p>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-40 bg-muted rounded-xl animate-pulse" />
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center justify-center py-16 text-center">
              <svg
                className="w-12 h-12 text-muted-foreground/50 mb-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <p className="text-lg font-medium text-muted-foreground">
                No skipped jobs yet
              </p>
              <p className="text-sm text-muted-foreground/70 mt-1">
                Jobs that require login will appear here with apply links
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {jobs.map((sj) => {
              const isExpanded = expandedId === sj.job.id;
              return (
                <Card key={sj.job.id} className="overflow-hidden">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <CardTitle className="text-base font-semibold truncate">
                          {sj.job.title}
                        </CardTitle>
                        <p className="text-sm text-muted-foreground mt-0.5">
                          {sj.job.company} &middot; {sj.job.location}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {sj.score > 0 && (
                          <Badge variant="secondary" className="text-xs">
                            {sj.score}% fit
                          </Badge>
                        )}
                        <Badge variant="outline" className="text-xs capitalize">
                          {sj.job.board}
                        </Badge>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="pt-0 space-y-3">
                    <div className="flex items-center gap-2">
                      <a
                        href={sj.job.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <Button size="sm" className="gap-1.5">
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
                          Apply on {sj.job.board}
                        </Button>
                      </a>
                      {(sj.tailored_resume || sj.cover_letter_template) && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            setExpandedId(isExpanded ? null : sj.job.id)
                          }
                        >
                          {isExpanded ? "Hide" : "Show"} Resume & Cover Letter
                        </Button>
                      )}
                    </div>

                    {isExpanded && (
                      <div className="space-y-4 pt-2 border-t border-border/50">
                        {sj.tailored_resume && (
                          <div>
                            <div className="flex items-center justify-between mb-2">
                              <h4 className="text-sm font-medium">
                                Tailored Resume
                              </h4>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 text-xs"
                                onClick={() =>
                                  copyToClipboard(
                                    sj.tailored_resume!.tailored_text,
                                    `resume-${sj.job.id}`
                                  )
                                }
                              >
                                {copiedField === `resume-${sj.job.id}`
                                  ? "Copied!"
                                  : "Copy"}
                              </Button>
                            </div>
                            <pre className="text-xs bg-muted/50 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto">
                              {sj.tailored_resume.tailored_text}
                            </pre>
                          </div>
                        )}

                        {sj.cover_letter_template && (
                          <div>
                            <div className="flex items-center justify-between mb-2">
                              <h4 className="text-sm font-medium">
                                Cover Letter
                              </h4>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 text-xs"
                                onClick={() =>
                                  copyToClipboard(
                                    sj.cover_letter_template,
                                    `cover-${sj.job.id}`
                                  )
                                }
                              >
                                {copiedField === `cover-${sj.job.id}`
                                  ? "Copied!"
                                  : "Copy"}
                              </Button>
                            </div>
                            <pre className="text-xs bg-muted/50 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto">
                              {sj.cover_letter_template}
                            </pre>
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
    </div>
  );
}
