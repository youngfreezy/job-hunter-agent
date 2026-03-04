"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { startSession } from "@/lib/api";

export default function NewSession() {
  const router = useRouter();
  const [keywords, setKeywords] = useState("");
  const [locations, setLocations] = useState("");
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [salaryMin, setSalaryMin] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    const keywordList = keywords.split(",").map((k) => k.trim()).filter(Boolean);
    const locationList = locations.split(",").map((l) => l.trim()).filter(Boolean);

    if (keywordList.length === 0) {
      setError("Enter at least one keyword.");
      return;
    }
    if (!resumeText.trim()) {
      setError("Paste your resume text.");
      return;
    }

    setLoading(true);
    try {
      const session = await startSession({
        keywords: keywordList,
        locations: locationList,
        remote_only: remoteOnly,
        salary_min: salaryMin ? parseInt(salaryMin) : undefined,
        resume_text: resumeText,
        linkedin_url: linkedinUrl || undefined,
        preferences: {},
      });
      router.push(`/session/${session.session_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start session");
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4 flex items-center justify-between max-w-7xl mx-auto">
        <Link href="/" className="text-xl font-bold tracking-tight">JobHunter Agent</Link>
        <Link href="/dashboard" className="text-sm text-zinc-600 dark:text-zinc-400 hover:text-zinc-900">
          Dashboard
        </Link>
      </nav>

      <div className="max-w-2xl mx-auto px-6 py-12">
        <h1 className="text-3xl font-bold mb-2">New Session</h1>
        <p className="text-zinc-600 dark:text-zinc-400 mb-8">
          Configure your job search. The AI will coach your resume, discover jobs, and apply for you.
        </p>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Keywords */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Search Keywords</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Input
                placeholder="e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
              />
              <p className="text-xs text-zinc-500">Comma-separated. These are matched against job titles and descriptions.</p>
              <div className="flex flex-wrap gap-2">
                {keywords.split(",").map((k) => k.trim()).filter(Boolean).map((k) => (
                  <Badge key={k} variant="secondary">{k}</Badge>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Location */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Location & Preferences</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Input
                placeholder="e.g. San Francisco, New York, Austin"
                value={locations}
                onChange={(e) => setLocations(e.target.value)}
              />
              <p className="text-xs text-zinc-500">Comma-separated cities. Leave blank for any location.</p>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={remoteOnly}
                    onChange={(e) => setRemoteOnly(e.target.checked)}
                    className="rounded"
                  />
                  Remote only
                </label>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-zinc-600">Min salary:</span>
                  <Input
                    type="number"
                    placeholder="e.g. 120000"
                    value={salaryMin}
                    onChange={(e) => setSalaryMin(e.target.value)}
                    className="w-32"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Resume */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Your Resume</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Textarea
                placeholder="Paste your full resume text here..."
                value={resumeText}
                onChange={(e) => setResumeText(e.target.value)}
                rows={12}
              />
              <p className="text-xs text-zinc-500">
                The AI Career Coach will analyze, score, and rewrite your resume before applying.
              </p>
            </CardContent>
          </Card>

          {/* LinkedIn */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">LinkedIn Profile (Optional)</CardTitle>
            </CardHeader>
            <CardContent>
              <Input
                placeholder="https://linkedin.com/in/yourprofile"
                value={linkedinUrl}
                onChange={(e) => setLinkedinUrl(e.target.value)}
              />
              <p className="text-xs text-zinc-500 mt-2">
                If provided, the Career Coach will advise on profile improvements.
              </p>
            </CardContent>
          </Card>

          {error && (
            <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded text-sm">
              {error}
            </div>
          )}

          <Button type="submit" size="lg" className="w-full" disabled={loading}>
            {loading ? "Starting session..." : "Start Job Hunt Session"}
          </Button>
        </form>
      </div>
    </div>
  );
}
