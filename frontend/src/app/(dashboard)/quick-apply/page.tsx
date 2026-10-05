// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import Link from "next/link";
import { SetupNotice } from "@/components/SetupNotice";
import { ResumeUpload, type ResumeAttachment } from "@/components/ResumeUpload";
import { startSession } from "@/lib/api";
import { quickApplyInitialUrls } from "@/lib/applicationAnswers";
import { indeedEasyApplyOnly } from "@/lib/indeed-policy";
import { validateJobUrls } from "@/lib/quick-apply-urls";
import { toast } from "sonner";

const URLS_STORAGE_KEY = "jh_quick_apply_urls";
const INDEED_DEMO = indeedEasyApplyOnly || process.env.NEXT_PUBLIC_BROWSERBASE_DEMO === "true";

export default function QuickApplyPage() {
  const router = useRouter();
  const [urls, setUrls] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [resumeAttachment, setResumeAttachment] = useState<ResumeAttachment | null>(null);
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showResumeUpload, setShowResumeUpload] = useState(false);

  useEffect(() => {
    let savedUrls = "";
    try { savedUrls = localStorage.getItem(URLS_STORAGE_KEY) || ""; } catch { /* Storage is optional. */ }
    setUrls(quickApplyInitialUrls(window.location.search, savedUrls));
  }, []);

  // Persist URLs as user types
  const handleUrlChange = useCallback((value: string) => {
    setUrls(value);
    try {
      localStorage.setItem(URLS_STORAGE_KEY, value);
    } catch {}
  }, []);

  const handleResumeReady = useCallback((text: string, attachment: ResumeAttachment | null) => {
    setResumeText(text);
    setResumeAttachment(attachment);
    if (attachment) setShowResumeUpload(false);
  }, []);

  const resumeReady = Boolean(resumeText && (resumeAttachment?.resumeUuid || resumeAttachment?.filePath));

  const { urls: parsedUrls, errors: urlErrors } = validateJobUrls(urls, INDEED_DEMO);

  // Domains that almost always require account creation (Workday, Taleo, etc.)
  const AUTH_DOMAINS = [
    "myworkdayjobs.com",
    "taleo.net",
    "icims.com",
    "apply.deloitte.com",
    "smartrecruiters.com",
  ];
  const authWarnings = parsedUrls.filter((u) =>
    AUTH_DOMAINS.some((d) => u.includes(d))
  );

  const handleSubmit = async () => {
    if (urlErrors.length) {
      toast.error(urlErrors[0]);
      return;
    }
    if (parsedUrls.length === 0) {
      toast.error("Paste at least one job URL.");
      return;
    }
    if (!resumeReady) {
      toast.error("Upload your resume first.");
      setShowResumeUpload(true);
      return;
    }

    setSubmitError("");
    setSubmitting(true);
    try {
      const session = await startSession({
        keywords: [],
        locations: ["Remote"],
        remote_only: false,
        salary_min: null,
        resume_text: resumeText,
        resume_file_path: resumeAttachment?.filePath || null,
        resume_uuid: resumeAttachment?.resumeUuid || null,
        linkedin_url: null,
        preferences: {},
        job_urls: parsedUrls,
        config: {
          max_jobs: parsedUrls.length,
          tailoring_quality: "standard",
          application_mode: "auto_apply",
          generate_cover_letters: true,
          job_boards: [],
          discovery_mode: "manual_urls",
          job_urls: parsedUrls,
        },
      });

      toast.success(`Session started with ${parsedUrls.length} jobs`);
      router.push(`/session/${session.session_id}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setSubmitError(msg || "Failed to start session");
      toast.error(msg || "Failed to start session");
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      <div className="mb-8">
        <h1 className="text-3xl font-bold">Quick Apply</h1>
        <p className="text-zinc-600 dark:text-zinc-400 mt-2">
          Paste job listing URLs to start applications using your resume.
          Review each result in session activity; some jobs may need your input.
        </p>
      </div>

      <SetupNotice />
      {/* Resume status */}
      <Card className="mb-6">
        <CardContent className="p-6">
          {resumeReady && !showResumeUpload && (
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-sm">Resume ready</p>
                <p className="text-xs text-zinc-500 mt-0.5">
                  Using {resumeAttachment?.fileName || "your saved resume"}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowResumeUpload(true)}
              >
                Change resume
              </Button>
            </div>
          )}
          <div className="space-y-3" hidden={resumeReady && !showResumeUpload}>
            <p className="font-medium text-sm">
              {resumeText ? "Upload a different resume" : "Upload your resume"}
            </p>
            <ResumeUpload onResumeReady={handleResumeReady} />
          </div>
        </CardContent>
      </Card>

      {/* URL input */}
      <Card className="mb-6">
        <CardContent className="p-6 space-y-4">
          <div>
            <h2 className="text-lg font-semibold">Job URLs</h2>
            <p className="text-sm text-zinc-500 mt-1">
              {INDEED_DEMO
                ? "Paste one Indeed Easy Apply listing per line. Browserbase uses your saved Indeed login; employer redirects and nested sign-ins are skipped."
                : "Paste one URL per line. Supports Greenhouse, Lever, Ashby, Workday, LinkedIn, and any direct job posting."}
            </p>
          </div>
          <textarea
            aria-label="Job URLs, one per line"
            aria-invalid={urlErrors.length > 0}
            aria-describedby="job-url-errors"
            className="w-full min-h-[180px] rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-4 py-3 text-sm font-mono placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-ring resize-y"
            placeholder={INDEED_DEMO ? "https://www.indeed.com/viewjob?jk=job-id" : `https://jobs.ashbyhq.com/company/job-id\nhttps://boards.greenhouse.io/company/jobs/12345\nhttps://jobs.lever.co/company/job-id`}
            value={urls}
            onChange={(e) => handleUrlChange(e.target.value)}
          />
          <div id="job-url-errors" role="alert" className="text-sm text-destructive">{urlErrors.map((error) => <p key={error}>{error}</p>)}</div>
          {parsedUrls.length > 0 && (
            <p className="text-xs text-zinc-500">
              {parsedUrls.length} valid URL{parsedUrls.length !== 1 ? "s" : ""}{" "}
              detected
            </p>
          )}
          {authWarnings.length > 0 && (
            <div className="rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/50 px-4 py-3">
              <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                {authWarnings.length} URL{authWarnings.length !== 1 ? "s" : ""} may
                require an account
              </p>
              <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                Workday, Taleo, and similar sites require login to apply. We
                don&apos;t support authenticated job boards — these URLs will be
                skipped.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {submitError && <p role="alert" className="mb-4 text-sm text-destructive">{submitError} <Link href="/settings" className="underline">Check setup in Settings</Link></p>}
      {/* Submit */}
      <Button
        onClick={handleSubmit}
        disabled={submitting || !resumeReady || parsedUrls.length === 0 || urlErrors.length > 0}
        className="w-full h-12 text-base font-semibold"
        size="lg"
      >
        {submitting
          ? "Starting session..."
          : `Apply to ${parsedUrls.length || 0} job${parsedUrls.length !== 1 ? "s" : ""}`}
      </Button>

      <p className="text-xs text-zinc-400 text-center mt-3">
        Clicking Apply starts applications to these jobs using your resume.
        Check session activity for questions that need your input and each application&apos;s result.
      </p>
    </div>
  );
}
