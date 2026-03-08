"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { API_BASE, getAuthHeaders } from "@/lib/api";

export default function CareerPivotPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Check for existing resume in localStorage
  const savedResume =
    typeof window !== "undefined"
      ? localStorage.getItem("jh_resume_text") || ""
      : "";

  async function handleStart() {
    if (!savedResume) {
      setError("Please upload a resume first via the Dashboard.");
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
          resume_text: savedResume,
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

      <div className="bg-card border rounded-lg p-8 text-center space-y-6">
        <div className="text-6xl">🔍</div>
        <h2 className="text-xl font-semibold">
          Analyze your AI automation risk
        </h2>
        <p className="text-muted-foreground max-w-lg mx-auto">
          We&apos;ll analyze your resume against O*NET and BLS data to find your
          automation risk score, adjacent roles you&apos;re qualified for, and a
          learning plan to close skill gaps.
        </p>

        {error && (
          <p className="text-destructive text-sm">{error}</p>
        )}

        <Button size="lg" onClick={handleStart} disabled={loading}>
          {loading ? "Analyzing..." : "Start Free Assessment"}
        </Button>

        <p className="text-xs text-muted-foreground">
          Powered by O*NET + BLS data. No credit card required.
        </p>
      </div>
    </div>
  );
}
