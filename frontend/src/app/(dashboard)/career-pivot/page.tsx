"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ResumeUpload } from "@/components/ResumeUpload";
import { API_BASE, getAuthHeaders } from "@/lib/api";

export default function CareerPivotPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasResume, setHasResume] = useState(false);

  useEffect(() => {
    setHasResume(!!(localStorage.getItem("jh_resume_text") || "").trim());
  }, []);

  async function handleStart() {
    const resumeText = localStorage.getItem("jh_resume_text") || "";
    if (!resumeText.trim()) {
      setError("Please upload your resume above first.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${API_BASE}/api/career-pivot`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text: resumeText,
          location: "Remote",
        }),
      });

      if (!res.ok) throw new Error(`Failed to start: ${res.statusText}`);
      const { session_id } = await res.json();
      router.push(`/career-pivot/${session_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "An unknown error occurred");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container mx-auto max-w-4xl p-6">
      <h1 className="text-3xl font-bold mb-2">Career Pivot Advisor</h1>
      <p className="text-muted-foreground mb-8">
        Is your job safe from AI? Find out in 60 seconds — free.
      </p>

      <div className="bg-card border rounded-lg p-8 space-y-6">
        <div className="text-center space-y-3">
          <div className="text-6xl">🔍</div>
          <h2 className="text-xl font-semibold">
            Analyze your AI automation risk
          </h2>
          <p className="text-muted-foreground max-w-lg mx-auto">
            We&apos;ll analyze your resume against O*NET and BLS data to find your
            automation risk score, adjacent roles you&apos;re qualified for, and a
            learning plan to close skill gaps.
          </p>
        </div>

        <div className="max-w-lg mx-auto">
          <ResumeUpload onResumeReady={() => setHasResume(true)} />
        </div>

        {error && (
          <p className="text-destructive text-sm text-center">{error}</p>
        )}

        <div className="text-center">
          <Button size="lg" onClick={handleStart} disabled={loading || !hasResume}>
            {loading ? "Analyzing..." : "Start Free Assessment"}
          </Button>
        </div>

        <p className="text-xs text-muted-foreground text-center">
          Powered by O*NET + BLS data. No credit card required.
        </p>
      </div>
    </div>
  );
}
