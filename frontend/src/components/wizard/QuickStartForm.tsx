// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Formik, Form, useFormikContext } from "formik";
import * as Yup from "yup";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { FormikFileUpload } from "@/components/forms/FormikFileUpload";
import { analyzeResume, startSession } from "@/lib/api";
import type { SessionFormValues } from "@/lib/schemas/session";
import { sessionInitialValues } from "@/lib/schemas/session";

const quickStartSchema = Yup.object({
  resumeText: Yup.string()
    .required("Upload a resume file (.pdf, .docx, or .txt).")
    .test(
      "has-email",
      "Your resume must include an email address so employers can contact you.",
      (value) => {
        if (!value) return false;
        return /[\w.+-]+@[\w-]+\.[\w.-]+/.test(value);
      }
    ),
  resumeFileName: Yup.string().default(""),
  resumeFilePath: Yup.string().default(""),
});

declare global {
  interface Window {
    umami?: { track: (event: string, data?: Record<string, unknown>) => void; identify: (data: Record<string, unknown>) => void };
  }
}

/** Inner component that watches Formik context for resume text changes. */
function QuickStartInner({ onAnalyzingChange }: { onAnalyzingChange?: (v: boolean) => void }) {
  const router = useRouter();
  const { values, isSubmitting } = useFormikContext<SessionFormValues>();
  const [keywords, setKeywords] = useState<string[]>([]);
  const [locations, setLocations] = useState<string[]>([]);
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzed, setAnalyzed] = useState(false);
  const [analyzeError, setAnalyzeError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [isNavigating, setIsNavigating] = useState(false);
  const [newKeyword, setNewKeyword] = useState("");
  const [newLocation, setNewLocation] = useState("");
  const analyzedTextRef = useRef("");
  const launchRef = useRef<HTMLButtonElement>(null);

  // Auto-analyze when resume text appears
  useEffect(() => {
    const text = values.resumeText;
    if (text && text.length >= 50 && text !== analyzedTextRef.current && !analyzing) {
      analyzedTextRef.current = text;
      setAnalyzing(true);
      onAnalyzingChange?.(true);
      setAnalyzeError("");
      analyzeResume(text)
        .then((result) => {
          setKeywords(result.keywords);
          setLocations(result.locations);
          setAnalyzed(true);
          window.umami?.track("quickstart-analyzed");
          // Auto-scroll to the Launch button after a short delay for render
          setTimeout(() => launchRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 150);
        })
        .catch((err) => {
          const msg = err instanceof Error ? err.message : "Analysis failed";
          setAnalyzeError(msg);
        })
        .finally(() => {
          setAnalyzing(false);
          onAnalyzingChange?.(false);
        });
    }
  }, [values.resumeText, analyzing, onAnalyzingChange]);

  const removeKeyword = (index: number) => {
    setKeywords((prev) => prev.filter((_, i) => i !== index));
  };

  const removeLocation = (index: number) => {
    setLocations((prev) => prev.filter((_, i) => i !== index));
  };

  const addKeyword = () => {
    const val = newKeyword.trim();
    if (val && !keywords.includes(val)) {
      setKeywords((prev) => [...prev, val]);
      setNewKeyword("");
    }
  };

  const addLocation = () => {
    const val = newLocation.trim();
    if (val && !locations.includes(val)) {
      setLocations((prev) => [...prev, val]);
      setNewLocation("");
    }
  };

  const handleRetryAnalysis = useCallback(() => {
    analyzedTextRef.current = "";
    setAnalyzed(false);
  }, []);

  const handleLaunch = async () => {
    setSubmitError("");
    if (keywords.length === 0) {
      setSubmitError("Upload your resume first so we can extract search keywords.");
      return;
    }
    setIsNavigating(true);
    try {
      // Merge saved AI settings from the session settings page
      let savedSettings: Record<string, unknown> = {};
      try {
        savedSettings = JSON.parse(localStorage.getItem("jh_session_settings") || "{}");
      } catch {}

      const session = await startSession({
        keywords,
        locations,
        remote_only: remoteOnly,
        salary_min: null,
        resume_text: values.resumeText,
        resume_file_path: values.resumeFilePath || null,
        linkedin_url: null,
        preferences: {},
        config: {
          max_jobs: (savedSettings.max_jobs as number) ?? 20,
          tailoring_quality: "standard",
          application_mode: (savedSettings.application_mode as string) ?? "auto_apply",
          generate_cover_letters: (savedSettings.generate_cover_letters as boolean) ?? true,
          job_boards: (savedSettings.job_boards as string[]) ?? ["linkedin", "indeed", "glassdoor", "ziprecruiter"],
          ai_temperature: (savedSettings.ai_temperature as number) ?? 0.0,
          scoring_strictness: (savedSettings.scoring_strictness as number) ?? 0.5,
        },
      });
      window.umami?.track("quickstart-complete");
      router.push(`/session/${session.session_id}`);
    } catch (err) {
      setIsNavigating(false);
      const msg = err instanceof Error ? err.message : "Failed to start session";
      if (msg === "Failed to fetch" || msg.includes("NetworkError") || msg === "Load failed") {
        setSubmitError(
          "Unable to connect to the server. Make sure the backend is running (npm start)."
        );
      } else {
        setSubmitError(msg);
      }
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="p-6 space-y-4">
          <div>
            <h2 className="text-lg font-semibold">Upload Your Resume</h2>
            <p className="text-sm text-zinc-500 mt-1">
              We&apos;ll extract your target roles and locations automatically.
            </p>
          </div>
          <FormikFileUpload />
        </CardContent>
      </Card>

      {analyzeError && (
        <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded text-sm">
          {analyzeError}
          <button type="button" onClick={handleRetryAnalysis} className="ml-2 underline">
            Retry
          </button>
        </div>
      )}

      {analyzed && keywords.length > 0 && (
        <Card>
          <CardContent className="p-6 space-y-4">
            <div>
              <p className="text-sm font-medium mb-2">Search Keywords</p>
              <div className="flex flex-wrap items-center gap-2 rounded-md border bg-background px-3 py-2 focus-within:ring-2 focus-within:ring-blue-500/30 focus-within:border-blue-500">
                {keywords.map((kw, i) => (
                  <Badge
                    key={i}
                    variant="secondary"
                    className="cursor-pointer hover:bg-red-100 hover:text-red-700 dark:hover:bg-red-900 dark:hover:text-red-300 transition-colors"
                    onClick={() => removeKeyword(i)}
                  >
                    {kw} &times;
                  </Badge>
                ))}
                <input
                  type="text"
                  value={newKeyword}
                  onChange={(e) => setNewKeyword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addKeyword();
                    }
                    if (e.key === "Backspace" && !newKeyword && keywords.length > 0) {
                      removeKeyword(keywords.length - 1);
                    }
                  }}
                  placeholder={
                    keywords.length === 0 ? "Type a keyword and press Enter…" : "Add more…"
                  }
                  className="flex-1 min-w-[120px] bg-transparent text-sm outline-none placeholder:text-zinc-400"
                />
              </div>
            </div>

            <div>
              <p className="text-sm font-medium mb-2">Locations</p>
              <div className="flex flex-wrap items-center gap-2 rounded-md border bg-background px-3 py-2 focus-within:ring-2 focus-within:ring-blue-500/30 focus-within:border-blue-500">
                {locations.map((loc, i) => (
                  <Badge
                    key={i}
                    variant="outline"
                    className="cursor-pointer hover:bg-red-100 hover:text-red-700 dark:hover:bg-red-900 dark:hover:text-red-300 transition-colors"
                    onClick={() => removeLocation(i)}
                  >
                    {loc} &times;
                  </Badge>
                ))}
                <Badge
                  variant={remoteOnly ? "default" : "outline"}
                  className={`cursor-pointer transition-colors ${
                    remoteOnly
                      ? "bg-blue-600 text-white hover:bg-blue-700"
                      : "hover:bg-blue-50 hover:text-blue-700 dark:hover:bg-blue-900 dark:hover:text-blue-300"
                  }`}
                  onClick={() => setRemoteOnly((prev) => !prev)}
                >
                  {remoteOnly ? "Remote" : "Remote"}
                </Badge>
                <input
                  type="text"
                  value={newLocation}
                  onChange={(e) => setNewLocation(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addLocation();
                    }
                    if (e.key === "Backspace" && !newLocation && locations.length > 0) {
                      removeLocation(locations.length - 1);
                    }
                  }}
                  placeholder={
                    locations.length === 0 && !remoteOnly
                      ? "Type a city and press Enter…"
                      : "Add more…"
                  }
                  className="flex-1 min-w-[120px] bg-transparent text-sm outline-none placeholder:text-zinc-400"
                />
              </div>
            </div>

            <div className="rounded-xl bg-zinc-50 p-3 text-sm text-zinc-500 dark:bg-zinc-900/60">
              Defaults: 20 jobs, auto-apply, all job boards, standard tailoring.
            </div>
          </CardContent>
        </Card>
      )}

      {submitError && (
        <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded text-sm">
          {submitError}
        </div>
      )}

      {analyzed && keywords.length > 0 && (
        <Button
          ref={launchRef}
          type="button"
          size="lg"
          className="w-full"
          disabled={isSubmitting || isNavigating || keywords.length === 0}
          onClick={handleLaunch}
        >
          {isNavigating ? (
            <span className="flex items-center gap-2">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              Launching...
            </span>
          ) : (
            "Launch Search"
          )}
        </Button>
      )}
    </div>
  );
}

export function QuickStartForm({ onAnalyzingChange }: { onAnalyzingChange?: (v: boolean) => void }) {
  return (
    <Formik<SessionFormValues>
      initialValues={sessionInitialValues}
      validationSchema={quickStartSchema}
      onSubmit={() => {
        /* submission handled by handleLaunch in QuickStartInner */
      }}
    >
      <Form>
        <QuickStartInner onAnalyzingChange={onAnalyzingChange} />
      </Form>
    </Formik>
  );
}
