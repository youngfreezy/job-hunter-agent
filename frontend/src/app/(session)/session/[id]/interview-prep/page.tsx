"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { API_BASE, getAuthHeaders } from "@/lib/api";
import AnswerGradeRadar from "@/components/charts/AnswerGradeRadar";
import ReadinessScoreBars from "@/components/charts/ReadinessScoreBars";

interface Question {
  id: string;
  category: string;
  question: string;
  source: string;
}

interface Grade {
  question_id: string;
  relevance: number;
  specificity: number;
  star_structure: number;
  confidence: number;
  overall: number;
  feedback: string;
  strong_answer_example: string;
}

interface CompanyBrief {
  mission: string;
  culture: string;
  recent_news: string;
  glassdoor_rating: number | null;
  things_to_mention: string[];
  interview_tips: string[];
}

interface InterviewReport {
  overall_readiness: number;
  category_scores?: Record<string, number>;
  focus_areas?: string[];
}

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

  // Start prep session
  async function handleStart(company: string, role: string, resumeText: string) {
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
    }
  }

  // SSE connection
  useEffect(() => {
    if (!prepId) return;
    const es = new EventSource(`${API_BASE}/api/interview-prep/${prepId}/stream`);

    es.addEventListener("company_brief", (e) => setBrief(JSON.parse(e.data)));
    es.addEventListener("questions_ready", (e) => {
      const data = JSON.parse(e.data);
      setQuestions(data.questions || []);
      setStatus("ready");
    });
    es.addEventListener("ready_for_practice", () => setStatus("practicing"));
    es.addEventListener("status", (e) => {
      const data = JSON.parse(e.data);
      setStatus(data.status);
    });
    es.addEventListener("done", () => es.close());
    es.addEventListener("error", (e) => {
      if (e instanceof MessageEvent) setError(JSON.parse(e.data).message);
      es.close();
    });
    es.onerror = () => es.close();

    return () => es.close();
  }, [prepId]);

  // Submit answer
  async function handleSubmitAnswer() {
    if (!prepId || !answer.trim()) return;
    setSubmitting(true);
    setLastGrade(null);

    try {
      const headers = await getAuthHeaders();
      const q = questions[currentQ];
      const res = await fetch(
        `${API_BASE}/api/interview-prep/${prepId}/answer`,
        {
          method: "POST",
          headers: { ...headers, "Content-Type": "application/json" },
          body: JSON.stringify({ question_id: q.id, answer }),
        }
      );
      if (!res.ok) throw new Error("Failed to grade answer");
      const data = await res.json();
      setLastGrade(data.grade);
      setGrades((prev) => [...prev, data.grade]);
      setAnswer("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "An unknown error occurred");
    } finally {
      setSubmitting(false);
    }
  }

  // End session
  async function handleEnd() {
    if (!prepId) return;
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE}/api/interview-prep/${prepId}/end`,
      { method: "POST", headers }
    );
    if (res.ok) {
      setReport(await res.json());
      setStatus("completed");
    }
  }

  // Not started yet — show start form
  if (!prepId) {
    const savedResume = typeof window !== "undefined" ? localStorage.getItem("jh_resume_text") || "" : "";
    return (
      <div className="container mx-auto max-w-3xl p-6 space-y-6">
        <h1 className="text-2xl font-bold">Interview Prep</h1>
        <p className="text-muted-foreground">
          Practice for your interview with AI-powered mock questions and real-time feedback.
        </p>
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
            onClick={() => {
              const company = (document.getElementById("company") as HTMLInputElement).value;
              const role = (document.getElementById("role") as HTMLInputElement).value;
              if (company && role) handleStart(company, role, savedResume);
            }}
          >
            Start Mock Interview
          </Button>
        </div>
      </div>
    );
  }

  const q = questions[currentQ];

  return (
    <div className="container mx-auto max-w-3xl p-6 space-y-6">
      <h1 className="text-2xl font-bold">Mock Interview</h1>

      {/* Loading */}
      {status === "connecting" && (
        <div className="bg-card border rounded-lg p-6 text-center">
          <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-muted-foreground">Preparing your interview...</p>
        </div>
      )}

      {/* Company Brief */}
      {brief && (
        <details className="bg-card border rounded-lg p-4" open>
          <summary className="cursor-pointer font-medium">Company Brief</summary>
          <div className="mt-3 space-y-2 text-sm">
            {brief.mission && <p><strong>Mission:</strong> {brief.mission}</p>}
            {brief.culture && <p><strong>Culture:</strong> {brief.culture}</p>}
            {brief.recent_news && <p><strong>Recent:</strong> {brief.recent_news}</p>}
            {brief.things_to_mention.length > 0 && (
              <div>
                <strong>Things to mention:</strong>
                <ul className="list-disc pl-5 mt-1">
                  {brief.things_to_mention.map((t, i) => <li key={i}>{t}</li>)}
                </ul>
              </div>
            )}
          </div>
        </details>
      )}

      {/* Question + Answer */}
      {q && status !== "completed" && (
        <div className="bg-card border rounded-lg p-6 space-y-4">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>Q{currentQ + 1} of {questions.length}</span>
            <span className="capitalize">{q.category.replace("_", " ")}</span>
          </div>
          <p className="text-lg font-medium">{q.question}</p>

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
            <Button variant="outline" onClick={() => { setCurrentQ(c => c + 1); setLastGrade(null); setAnswer(""); }}>
              Skip
            </Button>
            {grades.length > 0 && (
              <Button variant="secondary" onClick={handleEnd}>
                End & See Report
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Last Grade */}
      {lastGrade && (
        <div className="bg-card border rounded-lg p-6 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-medium">Score: {lastGrade.overall}/10</h3>
            <div className="w-32 bg-muted rounded-full h-2">
              <div className="bg-primary h-2 rounded-full" style={{ width: `${lastGrade.overall * 10}%` }} />
            </div>
          </div>
          <AnswerGradeRadar
            grade={lastGrade}
            averageGrades={grades.length > 1 ? {
              relevance: grades.reduce((s, g) => s + g.relevance, 0) / grades.length,
              specificity: grades.reduce((s, g) => s + g.specificity, 0) / grades.length,
              star_structure: grades.reduce((s, g) => s + g.star_structure, 0) / grades.length,
              confidence: grades.reduce((s, g) => s + g.confidence, 0) / grades.length,
            } : null}
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
