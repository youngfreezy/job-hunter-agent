// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { API_BASE, getAuthHeaders, getSSEToken, getWallet } from "@/lib/api";
import AnswerGradeRadar from "@/components/charts/AnswerGradeRadar";
import ReadinessScoreBars from "@/components/charts/ReadinessScoreBars";
import type {
  Question,
  Grade,
  CompanyBrief,
  InterviewReport,
  CoachingHints,
} from "@/lib/types/interview-prep";

export default function InterviewPrepPage() {
  const { id: sessionId } = useParams<{ id: string }>();
  const [prepId, setPrepId] = useState<string | null>(null);
  const [status, setStatus] = useState("idle");
  const [brief, setBrief] = useState<CompanyBrief | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentQ, setCurrentQ] = useState(0);
  const [answer, setAnswer] = useState("");
  const [grades, setGrades] = useState<Grade[]>([]);
  const [lastGrade, setLastGrade] = useState<Grade | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [report, setReport] = useState<InterviewReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [coaching, setCoaching] = useState<Record<string, CoachingHints>>({});
  const [coachingLoading, setCoachingLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [showPaywall, setShowPaywall] = useState(false);
  const [paid, setPaid] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const [walletBalance, setWalletBalance] = useState<number | null>(null);
  const maxFreeQuestions = 2;
  const router = useRouter();

  // Start prep session
  async function handleStart(company: string, role: string, resumeText: string) {
    setStarting(true);
    setError(null);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${API_BASE}/api/interview-prep`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          company,
          role,
          resume_text: resumeText,
          application_id: sessionId,
        }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.statusText}`);
      const data = await res.json();
      setPrepId(data.session_id);
      setStatus("connecting");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "An unknown error occurred");
      setStarting(false);
    }
  }

  // SSE connection
  useEffect(() => {
    if (!prepId) return;
    let es: EventSource | null = null;
    let cancelled = false;

    getSSEToken().then((token) => {
      if (cancelled) return;
      const sep = token ? `?token=${encodeURIComponent(token)}` : "";
      es = new EventSource(`${API_BASE}/api/interview-prep/${prepId}/stream${sep}`);

      es.addEventListener("company_brief", (e) => setBrief(JSON.parse(e.data)));
      es.addEventListener("questions_ready", (e) => {
        const data = JSON.parse(e.data);
        setQuestions(data.questions || []);
        setStatus("ready");
      });
      es.addEventListener("questions_unlocked", (e) => {
        const data = JSON.parse(e.data);
        setQuestions((prev) => [...prev, ...(data.questions || [])]);
      });
      es.addEventListener("ready_for_practice", () => setStatus("practicing"));
      es.addEventListener("status", (e) => {
        const data = JSON.parse(e.data);
        setStatus(data.status);
      });
      es.addEventListener("done", () => es?.close());
      es.addEventListener("error", (e) => {
        if (e instanceof MessageEvent) setError(JSON.parse(e.data).message);
        es?.close();
      });
      es.onerror = () => es?.close();
    });

    return () => {
      cancelled = true;
      es?.close();
    };
  }, [prepId]);

  // Submit answer
  async function handleSubmitAnswer() {
    if (!prepId || !answer.trim()) return;
    setSubmitting(true);
    setLastGrade(null);

    try {
      const headers = await getAuthHeaders();
      const q = questions[currentQ];
      const res = await fetch(`${API_BASE}/api/interview-prep/${prepId}/answer`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ question_id: q.id, answer }),
      });
      if (res.status === 402) {
        setShowPaywall(true);
        getWallet()
          .then((w) => setWalletBalance(w.balance))
          .catch(() => {});
        return;
      }
      if (!res.ok) throw new Error("Failed to grade answer");
      const data = await res.json();
      setLastGrade(data.grade);
      setGrades((prev) => [...prev, data.grade]);
      setAnswer("");
      if (!paid && data.questions_answered >= maxFreeQuestions) setShowPaywall(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "An unknown error occurred");
    } finally {
      setSubmitting(false);
    }
  }

  // Get coaching hints for current question
  async function handleGetCoaching() {
    if (!prepId || !q) return;
    if (coaching[q.id]) return; // already cached
    setCoachingLoading(true);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${API_BASE}/api/interview-prep/${prepId}/coach`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ question_id: q.id }),
      });
      if (res.status === 402) {
        setShowPaywall(true);
        getWallet()
          .then((w) => setWalletBalance(w.balance))
          .catch(() => {});
        return;
      }
      if (!res.ok) throw new Error("Failed to get coaching");
      const data = await res.json();
      setCoaching((prev) => ({ ...prev, [q.id]: data }));
    } catch {
      // Silently fail — coaching is optional
    } finally {
      setCoachingLoading(false);
    }
  }

  // End session
  async function handleEnd() {
    if (!prepId) return;
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE}/api/interview-prep/${prepId}/end`, {
      method: "POST",
      headers,
    });
    if (res.ok) {
      setReport(await res.json());
      setStatus("completed");
    }
  }

  // Unlock unlimited questions
  async function handleUnlock() {
    if (!prepId) return;
    setUnlocking(true);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${API_BASE}/api/interview-prep/${prepId}/unlock`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
      });
      if (res.status === 402) {
        router.push("/billing");
        return;
      }
      if (!res.ok) throw new Error("Unlock failed");
      setPaid(true);
      setShowPaywall(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to unlock");
    } finally {
      setUnlocking(false);
    }
  }

  const q = questions[currentQ];

  // Show start form / loading until questions arrive
  if (questions.length === 0 && !error && status !== "completed") {
    const savedResume =
      typeof window !== "undefined" ? localStorage.getItem("jh_resume_text") || "" : "";
    return (
      <div className="container mx-auto max-w-3xl p-6 space-y-6">
        <h1 className="text-2xl font-bold">Interview Prep</h1>
        <p className="text-muted-foreground">
          Practice for your interview with AI-powered mock questions and real-time feedback.
        </p>

        {starting ? (
          <div className="space-y-6 animate-in fade-in duration-300">
            <div className="bg-card border rounded-lg p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full" />
                <p className="text-sm text-muted-foreground">
                  {status === "researching" || status === "researching_company"
                    ? "Researching company culture & values..."
                    : status === "generating_questions"
                    ? "Generating personalized interview questions..."
                    : "Setting up your mock interview..."}
                </p>
              </div>
              <div className="w-full bg-muted rounded-full h-1.5">
                <div
                  className="bg-primary h-1.5 rounded-full animate-pulse transition-all duration-500"
                  style={{
                    width:
                      status === "researching" || status === "researching_company"
                        ? "50%"
                        : status === "generating_questions"
                        ? "80%"
                        : "30%",
                  }}
                />
              </div>
            </div>

            {/* Company brief skeleton */}
            <div className="bg-card border rounded-lg p-6 space-y-3">
              <div className="h-5 w-32 bg-muted animate-pulse rounded" />
              <div className="space-y-2">
                <div className="h-3 w-full bg-muted animate-pulse rounded" />
                <div className="h-3 w-4/5 bg-muted animate-pulse rounded" />
                <div className="h-3 w-3/5 bg-muted animate-pulse rounded" />
              </div>
            </div>

            {/* Question card skeleton */}
            <div className="bg-card border rounded-lg p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div className="h-4 w-20 bg-muted animate-pulse rounded" />
                <div className="h-4 w-24 bg-muted animate-pulse rounded" />
              </div>
              <div className="h-5 w-3/4 bg-muted animate-pulse rounded" />
              <div className="h-28 w-full bg-muted animate-pulse rounded" />
            </div>
          </div>
        ) : (
          <div className="bg-card border rounded-lg p-6 space-y-4">
            <input
              placeholder="Company name"
              className="w-full border rounded px-3 py-2 bg-background text-sm"
              id="company"
            />
            <input
              placeholder="Role title"
              className="w-full border rounded px-3 py-2 bg-background text-sm"
              id="role"
            />
            {error && <p className="text-destructive text-sm">{error}</p>}
            <Button
              loading={starting}
              onClick={() => {
                const company = (document.getElementById("company") as HTMLInputElement).value;
                const role = (document.getElementById("role") as HTMLInputElement).value;
                if (company && role) handleStart(company, role, savedResume);
              }}
            >
              Start Mock Interview
            </Button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-3xl p-6 space-y-6">
      <h1 className="text-2xl font-bold">Mock Interview</h1>

      {/* Company Brief */}
      {brief && (
        <details className="bg-card border rounded-lg p-4" open>
          <summary className="cursor-pointer font-medium">Company Brief</summary>
          <div className="mt-3 space-y-2 text-sm">
            {brief.mission && (
              <p>
                <strong>Mission:</strong> {brief.mission}
              </p>
            )}
            {brief.culture && (
              <p>
                <strong>Culture:</strong> {brief.culture}
              </p>
            )}
            {paid ? (
              <>
                {brief.recent_news && (
                  <p>
                    <strong>Recent:</strong> {brief.recent_news}
                  </p>
                )}
                {brief.things_to_mention.length > 0 && (
                  <div>
                    <strong>Things to mention:</strong>
                    <ul className="list-disc pl-5 mt-1">
                      {brief.things_to_mention.map((t, i) => (
                        <li key={i}>{t}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            ) : (
              <div className="mt-2 relative">
                <div className="blur-sm select-none pointer-events-none text-muted-foreground">
                  <p>
                    <strong>Recent:</strong> Company news and developments...
                  </p>
                  <p className="mt-1">
                    <strong>Things to mention:</strong>
                  </p>
                  <ul className="list-disc pl-5 mt-1">
                    <li>Key talking points tailored to this role...</li>
                    <li>Specific achievements to highlight...</li>
                  </ul>
                </div>
                <div className="absolute inset-0 flex items-center justify-center">
                  <button
                    onClick={handleUnlock}
                    disabled={unlocking}
                    className="text-sm font-medium bg-primary text-primary-foreground px-4 py-2 rounded-lg shadow-md hover:bg-primary/90 transition-colors cursor-pointer disabled:opacity-50"
                    title="Costs 1 credit — unlocks full company brief, unlimited questions, and AI coaching for this session"
                  >
                    {unlocking ? "Unlocking..." : "Unlock Full Brief — 1 Credit"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </details>
      )}

      {/* Question + Answer */}
      {q && status !== "completed" && (
        <div className="bg-card border rounded-lg p-6 space-y-4">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              Q{currentQ + 1} of {questions.length}
            </span>
            <div className="flex items-center gap-3">
              {!paid && currentQ < maxFreeQuestions && (
                <span className="text-xs text-yellow-400">
                  {maxFreeQuestions - currentQ - 1} free question
                  {maxFreeQuestions - currentQ - 1 !== 1 ? "s" : ""} left
                </span>
              )}
              <span className="capitalize">{q.category.replace("_", " ")}</span>
            </div>
          </div>
          <p className="text-lg font-medium">{q.question}</p>

          {/* Coaching hints */}
          {!coaching[q.id] && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleGetCoaching}
              disabled={coachingLoading}
              className="text-blue-400 border-blue-500/30 hover:bg-blue-500/10"
            >
              {coachingLoading ? (
                <>
                  <span className="animate-spin h-3.5 w-3.5 border-2 border-blue-400 border-t-transparent rounded-full mr-2" />
                  Analyzing your resume...
                </>
              ) : (
                "Get AI Coaching"
              )}
            </Button>
          )}

          {coaching[q.id] && (
            <div className="border border-blue-500/30 bg-blue-500/5 rounded-lg p-4 space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium text-blue-400">AI Coach</span>
                <button
                  onClick={() =>
                    setCoaching((prev) => {
                      const next = { ...prev };
                      delete next[q.id];
                      return next;
                    })
                  }
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  Hide
                </button>
              </div>

              {coaching[q.id].resume_highlights.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-1">
                    From your resume:
                  </p>
                  <ul className="space-y-1">
                    {coaching[q.id].resume_highlights.map((h, i) => (
                      <li
                        key={i}
                        className="text-muted-foreground pl-3 border-l-2 border-blue-500/30"
                      >
                        {h}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">
                  Structure your answer (Situation, Task, Action, Result):
                </p>
                <div className="grid grid-cols-1 gap-1.5">
                  {(["situation", "task", "action", "result"] as const).map((key) => (
                    <div key={key} className="flex gap-2">
                      <span className="font-semibold text-blue-400 uppercase text-xs w-16 shrink-0 pt-0.5">
                        {key[0]}
                      </span>
                      <span className="text-muted-foreground">
                        {coaching[q.id].star_scaffold[key]}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {coaching[q.id].key_points.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-1">
                    What they want to hear:
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {coaching[q.id].key_points.map((p, i) => (
                      <span
                        key={i}
                        className="px-2 py-0.5 bg-blue-500/10 text-blue-300 text-xs rounded-full border border-blue-500/20"
                      >
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {coaching[q.id].pitfalls.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-1">Avoid:</p>
                  <ul className="space-y-0.5">
                    {coaching[q.id].pitfalls.map((p, i) => (
                      <li key={i} className="text-yellow-400/80 text-xs">
                        &#x26A0; {p}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {showPaywall ? (
            <div className="border-2 border-primary/30 rounded-lg p-6 text-center space-y-4">
              <div className="text-3xl">&#128170;</div>
              <h3 className="text-lg font-semibold">
                You&apos;re doing great! Continue practicing?
              </h3>
              <p className="text-sm text-muted-foreground">
                You&apos;ve used your {maxFreeQuestions} free questions. Unlock unlimited questions
                and coaching for the rest of this session.
              </p>
              <div className="flex items-center justify-center gap-3">
                <Button onClick={handleUnlock} loading={unlocking} size="lg">
                  Unlock for 1 Credit
                </Button>
                <Button variant="outline" size="lg" onClick={() => router.push("/billing")}>
                  Buy Credits
                </Button>
              </div>
              {walletBalance !== null && (
                <p className="text-xs text-muted-foreground">
                  Current balance: {walletBalance} credit
                  {walletBalance !== 1 ? "s" : ""}
                </p>
              )}
              {grades.length > 0 && (
                <button
                  onClick={handleEnd}
                  className="text-sm text-muted-foreground hover:text-foreground underline"
                >
                  Or end session and see your report
                </button>
              )}
            </div>
          ) : (
            <>
              <textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="Type your answer..."
                rows={5}
                className="w-full border rounded px-3 py-2 bg-background text-sm resize-y"
              />

              <div className="flex gap-3">
                <Button onClick={handleSubmitAnswer} disabled={submitting || !answer.trim()}>
                  {submitting ? "Grading..." : "Submit Answer"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    if (!paid && currentQ + 1 >= maxFreeQuestions) {
                      setShowPaywall(true);
                      getWallet()
                        .then((w) => setWalletBalance(w.balance))
                        .catch(() => {});
                      return;
                    }
                    setCurrentQ((c) => c + 1);
                    setLastGrade(null);
                    setAnswer("");
                  }}
                >
                  Skip
                </Button>
                {grades.length > 0 && (
                  <Button variant="secondary" onClick={handleEnd}>
                    End & See Report
                  </Button>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* Last Grade */}
      {lastGrade && (
        <div className="bg-card border rounded-lg p-6 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-medium">Score: {lastGrade.overall}/10</h3>
            <div className="w-32 bg-muted rounded-full h-2">
              <div
                className="bg-primary h-2 rounded-full"
                style={{ width: `${lastGrade.overall * 10}%` }}
              />
            </div>
          </div>
          <AnswerGradeRadar
            grade={lastGrade}
            averageGrades={
              grades.length > 1
                ? {
                    relevance: grades.reduce((s, g) => s + g.relevance, 0) / grades.length,
                    specificity: grades.reduce((s, g) => s + g.specificity, 0) / grades.length,
                    star_structure:
                      grades.reduce((s, g) => s + g.star_structure, 0) / grades.length,
                    confidence: grades.reduce((s, g) => s + g.confidence, 0) / grades.length,
                  }
                : null
            }
          />
          <p className="text-sm text-muted-foreground">{lastGrade.feedback}</p>
          {lastGrade.strong_answer_example && (
            <details className="text-sm">
              <summary className="cursor-pointer text-primary">View strong answer example</summary>
              <p className="mt-2 text-muted-foreground">{lastGrade.strong_answer_example}</p>
            </details>
          )}
        </div>
      )}

      {/* Report */}
      {report && (
        <div className="bg-card border rounded-lg p-8 text-center space-y-4">
          <h2 className="text-lg font-medium">Readiness Report</h2>
          <div className="text-5xl font-bold text-primary">{report.overall_readiness}/10</div>
          {report.category_scores && (
            <div className="max-w-md mx-auto">
              <ReadinessScoreBars categoryScores={report.category_scores} />
            </div>
          )}
          {(report.focus_areas?.length ?? 0) > 0 && (
            <div className="text-sm text-muted-foreground">
              Focus areas: {report.focus_areas?.join(", ")}
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="bg-destructive/10 border border-destructive rounded-lg p-4">
          <p className="text-destructive">{error}</p>
        </div>
      )}
    </div>
  );
}
