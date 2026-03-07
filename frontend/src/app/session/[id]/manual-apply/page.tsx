"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getApplicationLog, type ApplicationLogEntry } from "@/lib/api";

type Tab = "all" | "failed" | "skipped" | "submitted";

const STATUS_COLORS: Record<string, string> = {
  submitted:
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  failed: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  skipped:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

export default function ManualApplyPage() {
  const { id: sessionId } = useParams<{ id: string }>();
  const [entries, setEntries] = useState<ApplicationLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);

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

  const filtered =
    tab === "all" ? entries : entries.filter((e) => e.status === tab);

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

  const downloadPdf = (title: string, content: string, filename: string) => {
    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(`<!DOCTYPE html><html><head><title>${title}</title>
      <style>
        body { font-family: Georgia, 'Times New Roman', serif; max-width: 700px; margin: 40px auto; padding: 20px; line-height: 1.6; color: #1a1a1a; font-size: 12pt; }
        h1 { font-size: 16pt; margin-bottom: 4px; }
        .meta { color: #666; font-size: 10pt; margin-bottom: 24px; }
        pre { white-space: pre-wrap; font-family: inherit; margin: 0; }
        @media print { body { margin: 0; } }
      </style>
    </head><body>
      <h1>${title}</h1>
      <div class="meta">${filename}</div>
      <pre>${content.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</pre>
      <script>window.print();</script>
    </body></html>`);
    win.document.close();
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
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

      <div className="flex-1 max-w-5xl mx-auto w-full px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold">Application Log</h1>
          <p className="text-muted-foreground mt-1">
            All application attempts with links, cover letters, and tailored
            resumes. Failed and skipped jobs can be applied to manually.
          </p>
        </div>

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
              <p className="text-lg font-medium text-muted-foreground">
                No applications yet
              </p>
              <p className="text-sm text-muted-foreground/70 mt-1">
                Application attempts will appear here as the agent processes
                jobs
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {filtered.map((entry, idx) => {
              const key = entry.job?.id || `entry-${idx}`;
              const isExpanded = expandedId === key;
              return (
                <Card key={key} className="overflow-hidden">
                  <CardContent className="py-4">
                    {/* Header row */}
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <Badge
                            className={`text-xs ${STATUS_COLORS[entry.status]}`}
                          >
                            {entry.status}
                          </Badge>
                          <span className="text-sm font-semibold truncate">
                            {entry.job?.title || "Unknown Position"}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {entry.job?.company || "Unknown Company"}
                          {entry.job?.location
                            ? ` · ${entry.job.location}`
                            : ""}
                          {entry.job?.board ? (
                            <Badge
                              variant="outline"
                              className="ml-2 text-[10px] py-0"
                            >
                              {entry.job.board}
                            </Badge>
                          ) : null}
                        </p>
                        {entry.error && (
                          <p className="text-xs text-red-500 mt-1 truncate">
                            {entry.error}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {entry.job?.url && (
                          <a
                            href={entry.job.url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            <Button
                              size="sm"
                              variant="outline"
                              className="gap-1 text-xs"
                            >
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
                        {(entry.tailored_resume || entry.cover_letter) && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-xs"
                            onClick={() =>
                              setExpandedId(isExpanded ? null : key)
                            }
                          >
                            {isExpanded ? "Hide" : "Details"}
                          </Button>
                        )}
                      </div>
                    </div>

                    {/* Expanded details */}
                    {isExpanded && (
                      <div className="space-y-4 pt-4 mt-4 border-t border-border/50">
                        {entry.cover_letter && (
                          <div>
                            <div className="flex items-center justify-between mb-2">
                              <h4 className="text-sm font-medium">
                                Cover Letter
                              </h4>
                              <div className="flex gap-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 text-xs"
                                  onClick={() =>
                                    copyToClipboard(
                                      entry.cover_letter,
                                      `cover-${key}`
                                    )
                                  }
                                >
                                  {copiedField === `cover-${key}`
                                    ? "Copied!"
                                    : "Copy"}
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 text-xs"
                                  onClick={() =>
                                    downloadPdf(
                                      "Cover Letter",
                                      entry.cover_letter,
                                      `${entry.job?.company || "Company"} — ${
                                        entry.job?.title || "Position"
                                      }`
                                    )
                                  }
                                >
                                  PDF
                                </Button>
                              </div>
                            </div>
                            <pre className="text-xs bg-muted/50 rounded-lg p-4 whitespace-pre-wrap max-h-48 overflow-y-auto">
                              {entry.cover_letter}
                            </pre>
                          </div>
                        )}
                        {entry.tailored_resume && (
                          <div>
                            <div className="flex items-center justify-between mb-2">
                              <h4 className="text-sm font-medium">
                                Tailored Resume
                                {entry.tailored_resume.fit_score > 0 && (
                                  <Badge
                                    variant="secondary"
                                    className="ml-2 text-xs"
                                  >
                                    {entry.tailored_resume.fit_score}% fit
                                  </Badge>
                                )}
                              </h4>
                              <div className="flex gap-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 text-xs"
                                  onClick={() =>
                                    copyToClipboard(
                                      entry.tailored_resume!.tailored_text,
                                      `resume-${key}`
                                    )
                                  }
                                >
                                  {copiedField === `resume-${key}`
                                    ? "Copied!"
                                    : "Copy"}
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 text-xs"
                                  onClick={() =>
                                    downloadPdf(
                                      "Tailored Resume",
                                      entry.tailored_resume!.tailored_text,
                                      `${entry.job?.company || "Company"} — ${
                                        entry.job?.title || "Position"
                                      }`
                                    )
                                  }
                                >
                                  PDF
                                </Button>
                              </div>
                            </div>
                            <pre className="text-xs bg-muted/50 rounded-lg p-4 whitespace-pre-wrap max-h-48 overflow-y-auto">
                              {entry.tailored_resume.tailored_text}
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
