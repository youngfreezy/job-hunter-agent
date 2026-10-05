// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useState } from "react";
import Link from "next/link";
import { responseError } from "@/lib/api-error";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ResumeUpload } from "@/components/ResumeUpload";
import { API_BASE, getAuthHeaders, apiFetch } from "@/lib/api";

export default function CareerPivotPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resumeText, setResumeText] = useState("");
  const hasResume = Boolean(resumeText.trim());

  async function handleStart() {
    if (!resumeText.trim()) {
      setError("Please upload your resume above first.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const headers = await getAuthHeaders();
      const res = await apiFetch(`${API_BASE}/api/career-pivot`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text: resumeText,
          location: "Remote",
        }),
      });

      if (!res.ok) throw new Error(await responseError(res, "Could not start this session."));
      const { session_id } = await res.json();
      router.push(`/career-pivot/${session_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "An unknown error occurred");
      setLoading(false);
    }
  }

  return (
    <div className="container mx-auto max-w-4xl px-4 py-6 sm:p-6">
      <h1 className="text-3xl font-bold mb-2">Career Pivot Advisor</h1>
      <p className="text-muted-foreground mb-8">
        Explore how AI may change your role and which skills to build next.
      </p>

      <div className="bg-card border rounded-lg p-8 space-y-6">
        <div className="text-center space-y-3">
          <div className="text-6xl">🔍</div>
          <h2 className="text-xl font-semibold">Analyze your AI automation risk</h2>
          <p className="text-muted-foreground max-w-lg mx-auto">
            We&apos;ll analyze your resume against U.S. Department of Labor data to find your
            automation risk score, adjacent roles you&apos;re qualified for, and a learning plan to
            close skill gaps.
          </p>
        </div>

        <div className="max-w-lg mx-auto">
          <ResumeUpload onResumeReady={setResumeText} />
        </div>

        {error && <div role="alert" className="text-destructive text-sm text-center"><p>{error}</p><Link href="/settings" className="underline">Check API keys in Settings</Link></div>}

        <div className="text-center">
          <Button size="lg" onClick={handleStart} disabled={!hasResume} loading={loading}>
            Start Assessment
          </Button>
        </div>

        <p className="text-xs text-muted-foreground text-center">
          Uses U.S. Department of Labor data. Your model provider bills API usage separately.
        </p>
      </div>
    </div>
  );
}
