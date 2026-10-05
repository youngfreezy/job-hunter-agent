// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { readSavedResume } from "@/lib/resume-storage";

import { RecoveryNotice } from "@/components/RecoveryNotice";
import { Button } from "@/components/ui/button";
import { API_BASE, apiFetch, createAuthenticatedStream, getAuthHeaders, getWallet, type SSEConnection } from "@/lib/api";
import { resultStreamError } from "@/lib/result-stream";
import type {
  CoachingHints,
  CompanyBrief,
  Grade,
  InterviewReport,
  Question,
} from "@/lib/types/interview-prep";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { CompanyBriefPanel } from "@/components/interview-prep/CompanyBriefPanel";

import { InterviewAnswerGrade } from "@/components/interview-prep/InterviewAnswerGrade";

import { InterviewReadinessReport } from "@/components/interview-prep/InterviewReadinessReport";

import { InterviewQuestion } from "@/components/interview-prep/InterviewQuestion";

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
  const [streamAttempt, setStreamAttempt] = useState(0);
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
      const res = await apiFetch(`${API_BASE}/api/interview-prep`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          company,
          role,
          resume_text: resumeText,
          application_id: sessionId,
        }),
      });
      if(!res.ok) throw new Error(`Failed: ${res.statusText}`);
      const data = await res.json();
      setPrepId(data.session_id);
      setStatus("connecting");
    } catch(err: unknown) {
      setError(err instanceof Error ? err.message : "An unknown error occurred");
      setStarting(false);
    }
  }

  // SSE connection
  useEffect(() => {
    if(!prepId) return;
    let es: SSEConnection | null = null;
    es = createAuthenticatedStream(`${API_BASE}/api/interview-prep/${prepId}/stream`);

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
    es.addEventListener("error", (event) => {
      setError(resultStreamError(event));
      es?.close();
    });

    return () => {
      es?.close();
    };
  }, [prepId, streamAttempt]);

  function handleSkipQuestion() {
    if(!paid && currentQ + 1 >= maxFreeQuestions) {
      setShowPaywall(true);
      getWallet()
        .then((w) => setWalletBalance(w.balance))
        .catch(() => { });
      return;
    }
    setCurrentQ((c) => c + 1);
    setLastGrade(null);
    setAnswer("");
  }

  // Submit answer
  async function handleSubmitAnswer() {
    if(!prepId || !answer.trim()) return;
    setSubmitting(true);
    setLastGrade(null);

    try {
      const headers = await getAuthHeaders();
      const q = questions[currentQ];
      const res = await apiFetch(`${API_BASE}/api/interview-prep/${prepId}/answer`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ question_id: q.id, answer }),
      });
      if(res.status === 402) {
        setShowPaywall(true);
        getWallet()
          .then((w) => setWalletBalance(w.balance))
          .catch(() => { });
        return;
      }
      if(!res.ok) throw new Error("Failed to grade answer");
      const data = await res.json();
      setLastGrade(data.grade);
      setGrades((prev) => [...prev, data.grade]);
      setAnswer("");
      if(!paid && data.questions_answered >= maxFreeQuestions) setShowPaywall(true);
    } catch(err: unknown) {
      setError(err instanceof Error ? err.message : "An unknown error occurred");
    } finally {
      setSubmitting(false);
    }
  }

  // Get coaching hints for current question
  async function handleGetCoaching() {
    if(!prepId || !q) return;
    if(coaching[q.id]) return; // already cached
    setCoachingLoading(true);
    try {
      const headers = await getAuthHeaders();
      const res = await apiFetch(`${API_BASE}/api/interview-prep/${prepId}/coach`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ question_id: q.id }),
      });
      if(res.status === 402) {
        setShowPaywall(true);
        getWallet()
          .then((w) => setWalletBalance(w.balance))
          .catch(() => { });
        return;
      }
      if(!res.ok) throw new Error("Failed to get coaching");
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
    if(!prepId) return;
    const headers = await getAuthHeaders();
    const res = await apiFetch(`${API_BASE}/api/interview-prep/${prepId}/end`, {
      method: "POST",
      headers,
    });
    if(res.ok) {
      setReport(await res.json());
      setStatus("completed");
    }
  }

  // Unlock unlimited questions
  async function handleUnlock() {
    if(!prepId) return;
    setUnlocking(true);
    try {
      const headers = await getAuthHeaders();
      const res = await apiFetch(`${API_BASE}/api/interview-prep/${prepId}/unlock`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
      });
      if(res.status === 402) {
        router.push("/billing");
        return;
      }
      if(!res.ok) throw new Error("Unlock failed");
      setPaid(true);
      setShowPaywall(false);
    } catch(e) {
      setError(e instanceof Error ? e.message : "Failed to unlock");
    } finally {
      setUnlocking(false);
    }
  }

  const q = questions[currentQ];

  // Show start form / loading until questions arrive
  if(questions.length === 0 && !error && status !== "completed") {
    const savedResume = readSavedResume().text;
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
                    ? "Generating an AI company briefing..."
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
                if(company && role) handleStart(company, role, savedResume);
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

      <CompanyBriefPanel brief={brief} paid={paid} unlocking={unlocking} handleUnlock={handleUnlock} />

      <InterviewQuestion q={q} status={status} currentQ={currentQ} questions={questions} paid={paid} maxFreeQuestions={maxFreeQuestions} coaching={coaching} setCoaching={setCoaching} coachingLoading={coachingLoading} handleGetCoaching={handleGetCoaching} showPaywall={showPaywall} unlocking={unlocking} handleUnlock={handleUnlock} onBuyCredits={() => router.push("/billing")} walletBalance={walletBalance} grades={grades} handleEnd={handleEnd} answer={answer} setAnswer={setAnswer} handleSubmitAnswer={handleSubmitAnswer} submitting={submitting} handleSkipQuestion={handleSkipQuestion} />

      <InterviewAnswerGrade lastGrade={lastGrade} grades={grades} />

      <InterviewReadinessReport report={report} />

      {error && <RecoveryNotice message={error} retryLabel={prepId ? "Retry connection" : "Back to form"} onRetry={() => { setError(null); setStarting(Boolean(prepId)); setStreamAttempt((value) => value + 1); }} />}
    </div>
  );
}
