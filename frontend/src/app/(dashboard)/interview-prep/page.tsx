// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ResumeUpload } from "@/components/ResumeUpload";
import { API_BASE, getAuthHeaders, apiFetch } from "@/lib/api";

export default function InterviewPrepLandingPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasResume, setHasResume] = useState(false);
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");

  useEffect(() => {
    setHasResume(!!(localStorage.getItem("jh_resume_text") || "").trim());
  }, []);

  async function handleStart() {
    const resumeText = localStorage.getItem("jh_resume_text") || "";
    if (!resumeText.trim()) {
      setError("Please upload your resume first.");
      return;
    }
    if (!company.trim() || !role.trim()) {
      setError("Please enter both a company name and role.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const headers = await getAuthHeaders();
      const res = await apiFetch(`${API_BASE}/api/interview-prep`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          company: company.trim(),
          role: role.trim(),
          resume_text: resumeText,
        }),
      });

      if (!res.ok) throw new Error(`Failed to start: ${res.statusText}`);
      const { session_id } = await res.json();
      router.push(`/interview-prep/${session_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "An unknown error occurred");
      setLoading(false);
    }
  }

  return (
    <div className="container mx-auto max-w-4xl px-4 py-6 sm:p-6">
      <h1 className="text-3xl font-bold mb-2">Interview Prep</h1>
      <p className="text-muted-foreground mb-8">
        Practice with AI-powered mock interviews tailored to your resume and target role.
      </p>

      <div className="bg-card border rounded-lg p-8 space-y-6">
        <div className="text-center space-y-3">
          <div className="text-6xl">🎯</div>
          <h2 className="text-xl font-semibold">Mock interview with AI coaching</h2>
          <p className="text-muted-foreground max-w-lg mx-auto">
            We&apos;ll research the company, generate personalized interview questions, and coach
            you through answers using your resume. Get real-time grading on every response.
          </p>
        </div>

        <div className="max-w-lg mx-auto space-y-4">
          <ResumeUpload onResumeReady={() => setHasResume(true)} />

          <input
            placeholder="Company name (e.g. Google)"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            className="w-full border rounded px-3 py-2 bg-background text-sm"
          />
          <input
            placeholder="Role title (e.g. Senior Software Engineer)"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="w-full border rounded px-3 py-2 bg-background text-sm"
          />
        </div>

        {error && <p className="text-destructive text-sm text-center">{error}</p>}

        <div className="text-center">
          <Button
            size="lg"
            onClick={handleStart}
            disabled={!hasResume || !company.trim() || !role.trim()}
            loading={loading}
          >
            Start Mock Interview
          </Button>
        </div>

        <p className="text-xs text-muted-foreground text-center">
          Includes company research, structured answer coaching, and answer grading.
        </p>
      </div>
    </div>
  );
}
