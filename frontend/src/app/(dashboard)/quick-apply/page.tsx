// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ResumeUpload } from "@/components/ResumeUpload";
import { startSession } from "@/lib/api";
import { toast } from "sonner";

const RESUME_TEXT_KEY = "jh_resume_text";
const RESUME_FILENAME_KEY = "jh_resume_filename";
const RESUME_UUID_KEY = "jh_resume_uuid";
const URLS_STORAGE_KEY = "jh_quick_apply_urls";

export default function QuickApplyPage() {
  const router = useRouter();
  const [urls, setUrls] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [resumeFileName, setResumeFileName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showResumeUpload, setShowResumeUpload] = useState(false);

  // Restore saved resume from localStorage
  useEffect(() => {
    const saved = localStorage.getItem(RESUME_TEXT_KEY) || "";
    const savedName = localStorage.getItem(RESUME_FILENAME_KEY) || "";
    setResumeText(saved);
    setResumeFileName(savedName);
    if (!saved) setShowResumeUpload(true);

    // Restore saved URLs
    const savedUrls = localStorage.getItem(URLS_STORAGE_KEY) || "";
    if (savedUrls) setUrls(savedUrls);
  }, []);

  // Persist URLs as user types
  const handleUrlChange = useCallback((value: string) => {
    setUrls(value);
    try {
      localStorage.setItem(URLS_STORAGE_KEY, value);
    } catch {}
  }, []);

  const handleResumeReady = useCallback((text: string) => {
    setResumeText(text);
    const name = localStorage.getItem(RESUME_FILENAME_KEY) || "resume.pdf";
    setResumeFileName(name);
  }, []);

  const parsedUrls = urls
    .split("\n")
    .map((u) => u.trim())
    .filter((u) => u.startsWith("http"));

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
    if (parsedUrls.length === 0) {
      toast.error("Paste at least one job URL.");
      return;
    }
    if (!resumeText) {
      toast.error("Upload your resume first.");
      setShowResumeUpload(true);
      return;
    }

    setSubmitting(true);
    try {
      const session = await startSession({
        keywords: [],
        locations: ["Remote"],
        remote_only: false,
        salary_min: null,
        resume_text: resumeText,
        resume_file_path: null,
        resume_uuid: localStorage.getItem(RESUME_UUID_KEY) || null,
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
      toast.error(msg || "Failed to start session");
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      <div className="mb-8">
        <h1 className="text-3xl font-bold">Quick Apply</h1>
        <p className="text-zinc-600 dark:text-zinc-400 mt-2">
          Paste job listing URLs and we&apos;ll apply to all of them using your
          resume. No search needed — go straight to applications.
        </p>
      </div>

      {/* Resume status */}
      <Card className="mb-6">
        <CardContent className="p-6">
          {resumeText && !showResumeUpload ? (
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-sm">Resume ready</p>
                <p className="text-xs text-zinc-500 mt-0.5">
                  Using {resumeFileName || "your saved resume"}
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
          ) : (
            <div className="space-y-3">
              <p className="font-medium text-sm">
                {resumeText ? "Upload a different resume" : "Upload your resume"}
              </p>
              <ResumeUpload
                onResumeReady={(text) => {
                  handleResumeReady(text);
                  setShowResumeUpload(false);
                }}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* URL input */}
      <Card className="mb-6">
        <CardContent className="p-6 space-y-4">
          <div>
            <h2 className="text-lg font-semibold">Job URLs</h2>
            <p className="text-sm text-zinc-500 mt-1">
              Paste one URL per line. Supports Greenhouse, Lever, Ashby,
              Workday, LinkedIn, and any direct job posting.
            </p>
          </div>
          <textarea
            className="w-full min-h-[180px] rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-4 py-3 text-sm font-mono placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
            placeholder={`https://jobs.ashbyhq.com/company/job-id\nhttps://boards.greenhouse.io/company/jobs/12345\nhttps://jobs.lever.co/company/job-id`}
            value={urls}
            onChange={(e) => handleUrlChange(e.target.value)}
          />
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

      {/* Submit */}
      <Button
        onClick={handleSubmit}
        disabled={submitting || parsedUrls.length === 0}
        className="w-full h-12 text-base font-semibold"
        size="lg"
      >
        {submitting
          ? "Starting session..."
          : `Apply to ${parsedUrls.length || 0} job${parsedUrls.length !== 1 ? "s" : ""}`}
      </Button>

      <p className="text-xs text-zinc-400 text-center mt-3">
        Your resume will be tailored for each position. You&apos;ll review the
        shortlist before any applications are submitted.
      </p>
    </div>
  );
}
