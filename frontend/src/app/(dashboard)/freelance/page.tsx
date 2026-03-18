// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ResumeUpload } from "@/components/ResumeUpload";
import { API_BASE, getAuthHeaders, apiFetch } from "@/lib/api";

const PLATFORMS = [
  { id: "upwork", label: "Upwork" },
  { id: "linkedin", label: "LinkedIn (contract)" },
  { id: "fiverr", label: "Fiverr Pro" },
  { id: "freelancer", label: "Freelancer.com" },
];

export default function FreelancePage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rateMin, setRateMin] = useState(50);
  const [rateMax, setRateMax] = useState(120);
  const [platforms, setPlatforms] = useState(["upwork", "linkedin"]);
  const [availability, setAvailability] = useState("part_time");
  const [hasResume, setHasResume] = useState(false);

  useEffect(() => {
    setHasResume(!!(localStorage.getItem("jh_resume_text") || "").trim());
  }, []);

  function togglePlatform(id: string) {
    setPlatforms((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]));
  }

  async function handleStart() {
    const savedResume = localStorage.getItem("jh_resume_text") || "";
    if (!savedResume.trim()) {
      setError("Please upload your resume above first.");
      return;
    }
    if (platforms.length === 0) {
      setError("Select at least one platform.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const headers = await getAuthHeaders();
      const res = await apiFetch(`${API_BASE}/api/freelance`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text: localStorage.getItem("jh_resume_text") || "",
          hourly_rate_min: rateMin,
          hourly_rate_max: rateMax,
          platforms,
          project_types: [],
          availability,
        }),
      });

      if (!res.ok) throw new Error(`Failed to start: ${res.statusText}`);
      const { session_id } = await res.json();
      router.push(`/freelance/${session_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "An unknown error occurred");
    }
  }

  return (
    <div className="container mx-auto max-w-4xl px-4 py-6 sm:p-6">
      <h1 className="text-3xl font-bold mb-2">Freelance Gig Finder</h1>
      <p className="text-muted-foreground mb-8">
        Find gigs free. Submit unlimited proposals for one flat price.
      </p>

      <div className="bg-card border rounded-lg p-6 space-y-6">
        <p className="text-muted-foreground text-sm">
          Upload your resume and we&apos;ll scan top freelance platforms for gigs matching your skills,
          generate tailored proposals, and help you apply — all in one session.
        </p>

        <ResumeUpload onResumeReady={() => setHasResume(true)} />

        <div>
          <label className="block text-sm font-medium mb-2">Hourly Rate Range</label>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">$</span>
              <input
                type="number"
                value={rateMin}
                onChange={(e) => setRateMin(Number(e.target.value))}
                className="w-20 rounded border bg-background px-2 py-1 text-sm"
              />
            </div>
            <span className="text-muted-foreground">—</span>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">$</span>
              <input
                type="number"
                value={rateMax}
                onChange={(e) => setRateMax(Number(e.target.value))}
                className="w-20 rounded border bg-background px-2 py-1 text-sm"
              />
            </div>
            <span className="text-muted-foreground text-sm">/hr</span>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Platforms to Search</label>
          <div className="flex flex-wrap gap-2">
            {PLATFORMS.map((p) => (
              <button
                key={p.id}
                onClick={() => togglePlatform(p.id)}
                className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
                  platforms.includes(p.id)
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-background text-muted-foreground border-muted hover:border-foreground"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Availability</label>
          <div className="flex flex-wrap gap-3">
            {[
              { id: "full_time", label: "Full-time freelance" },
              { id: "part_time", label: "Part-time / side gigs" },
            ].map((opt) => (
              <button
                key={opt.id}
                onClick={() => setAvailability(opt.id)}
                className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
                  availability === opt.id
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-background text-muted-foreground border-muted hover:border-foreground"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {error && <p className="text-destructive text-sm">{error}</p>}

        <Button
          size="lg"
          className="w-full"
          onClick={handleStart}
          disabled={!hasResume}
          loading={loading}
        >
          Start Searching
        </Button>
      </div>
    </div>
  );
}
