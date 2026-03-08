"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { API_BASE, getAuthHeaders, getWallet } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ResumeUpload } from "@/components/ResumeUpload";
import TaskRiskBars from "@/components/charts/TaskRiskBars";
import PivotComparisonScatter from "@/components/charts/PivotComparisonScatter";
import SkillGapRadar from "@/components/charts/SkillGapRadar";

interface TaskBreakdown {
  task: string;
  risk_pct: number;
  onet_activity_id?: string;
}

interface LearningResource {
  name: string;
  hours: number;
  cost: string;
}

interface LearningWeek {
  week: string | number;
  topic: string;
  resources?: LearningResource[];
}

interface SkillComparison {
  categories: string[];
  user_scores: number[];
  target_scores: number[];
}

interface PivotRole {
  role: string;
  soc_code?: string;
  skill_overlap_pct: number;
  salary_range: { min: number; max: number; median: number };
  market_demand: number;
  growth_rate?: string;
  entry_education?: string;
  ai_risk_pct: number;
  missing_skills: string[];
  skill_comparison?: SkillComparison;
  learning_plan: LearningWeek[];
  time_to_pivot_weeks: number;
}

interface RiskAssessment {
  automation_risk_score: number;
  task_breakdown: TaskBreakdown[];
  resistant_abilities?: string[];
  parsed_role: string;
  parsed_skills: string[];
  years_experience: number;
  industry: string;
  soc_code?: string;
}

export default function SessionCareerPivotPage() {
  const { id: sessionId } = useParams<{ id: string }>();
  const router = useRouter();
  const [pivotId, setPivotId] = useState<string | null>(null);
  const [status, setStatus] = useState("idle");
  const [statusMessage, setStatusMessage] = useState("");
  const [risk, setRisk] = useState<RiskAssessment | null>(null);
  const [pivots, setPivots] = useState<PivotRole[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expandedRadar, setExpandedRadar] = useState<number | null>(null);
  const [paywall, setPaywall] = useState<{ count: number; message: string; cost: number } | null>(null);
  const [unlocking, setUnlocking] = useState(false);
  const [walletBalance, setWalletBalance] = useState<number | null>(null);
  const [starting, setStarting] = useState(false);
  const [hasResume, setHasResume] = useState(false);

  useEffect(() => {
    setHasResume(!!(localStorage.getItem("jh_resume_text") || "").trim());
  }, []);

  // Start pivot session
  async function handleStart() {
    const resumeText = localStorage.getItem("jh_resume_text") || "";
    if (!resumeText.trim()) {
      setError("Please upload your resume first.");
      return;
    }
    setStarting(true);
    setError(null);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${API_BASE}/api/career-pivot`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ resume_text: resumeText, location: "Remote" }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.statusText}`);
      const { session_id } = await res.json();
      setPivotId(session_id);
      setStatus("connecting");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "An unknown error occurred");
      setStarting(false);
    }
  }

  // SSE connection
  useEffect(() => {
    if (!pivotId) return;
    const es = new EventSource(`${API_BASE}/api/career-pivot/${pivotId}/stream`);

    es.addEventListener("status", (e) => {
      const data = JSON.parse(e.data);
      setStatus(data.status);
      setStatusMessage(data.message);
    });

    es.addEventListener("risk_assessment", (e) => {
      setRisk(JSON.parse(e.data));
    });

    es.addEventListener("pivot_roles", (e) => {
      const data = JSON.parse(e.data);
      setPivots(data.recommended_pivots || []);
      setPaywall(null);
    });

    es.addEventListener("paywall", (e) => {
      const data = JSON.parse(e.data);
      setPaywall({ count: data.count, message: data.message, cost: data.cost });
      getWallet().then((w) => setWalletBalance(w.balance)).catch(() => {});
    });

    es.addEventListener("done", () => {
      setStatus("completed");
      setStatusMessage("Analysis complete!");
      es.close();
    });

    es.addEventListener("error", (e) => {
      if (e instanceof MessageEvent) {
        setError(JSON.parse(e.data).message);
      }
      es.close();
    });

    es.onerror = () => es.close();
    return () => es.close();
  }, [pivotId]);

  function riskColor(score: number) {
    if (score >= 70) return "text-red-500";
    if (score >= 40) return "text-yellow-500";
    return "text-green-500";
  }

  function riskLabel(score: number) {
    if (score >= 70) return "HIGH RISK";
    if (score >= 40) return "MODERATE RISK";
    return "LOW RISK";
  }

  async function handleUnlock() {
    if (!pivotId) return;
    setUnlocking(true);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_BASE}/api/career-pivot/${pivotId}/unlock`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
      });
      if (res.status === 402) {
        router.push("/billing");
        return;
      }
      if (!res.ok) throw new Error("Unlock failed");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to unlock");
    } finally {
      setUnlocking(false);
    }
  }

  // Not started yet — show start form
  if (!pivotId) {
    return (
      <div className="container mx-auto max-w-4xl p-6 space-y-6">
        <h1 className="text-2xl font-bold">Career Pivot Advisor</h1>
        <p className="text-muted-foreground">
          Is your job safe from AI? Find out in 60 seconds — free.
        </p>

        {starting ? (
          <div className="bg-card border rounded-lg p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full" />
              <p className="text-sm text-muted-foreground">
                Starting your career pivot analysis...
              </p>
            </div>
            <div className="w-full bg-muted rounded-full h-1.5">
              <div className="bg-primary h-1.5 rounded-full animate-pulse" style={{ width: "25%" }} />
            </div>
          </div>
        ) : (
          <div className="bg-card border rounded-lg p-8 space-y-6">
            <div className="text-center space-y-3">
              <h2 className="text-xl font-semibold">Analyze your AI automation risk</h2>
              <p className="text-muted-foreground max-w-lg mx-auto">
                We&apos;ll analyze your resume against U.S. Department of Labor data to find your
                automation risk score, adjacent roles you&apos;re qualified for, and a learning plan
                to close skill gaps.
              </p>
            </div>

            <div className="max-w-lg mx-auto">
              <ResumeUpload onResumeReady={() => setHasResume(true)} />
            </div>

            {error && <p className="text-destructive text-sm text-center">{error}</p>}

            <div className="text-center">
              <Button size="lg" onClick={handleStart} disabled={!hasResume} loading={starting}>
                Start Free Assessment
              </Button>
            </div>

            <p className="text-xs text-muted-foreground text-center">
              Powered by U.S. Department of Labor data. No credit card required.
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-4xl p-6 space-y-8">
      <h1 className="text-2xl font-bold">Career Pivot Analysis</h1>

      {/* Status — hide once we have risk data */}
      {status !== "completed" && !error && !risk && (
        <div className="bg-card border rounded-lg p-6 text-center">
          <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-muted-foreground">{statusMessage}</p>
        </div>
      )}

      {/* Secondary loading — show when risk is loaded but pivots still pending and no paywall yet */}
      {risk && pivots.length === 0 && !paywall && status !== "completed" && !error && (
        <div className="bg-card border rounded-lg p-4 flex items-center gap-3">
          <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full" />
          <p className="text-sm text-muted-foreground">Finding recommended pivot roles...</p>
        </div>
      )}

      {/* Paywall — unlock pivot roles with blurred chart preview */}
      {paywall && pivots.length === 0 && (
        <div className="space-y-4">
          <div className="bg-card border rounded-lg p-6 relative overflow-hidden">
            <div className="blur-sm select-none pointer-events-none opacity-60">
              <h2 className="text-lg font-medium mb-2">Pivot Role Comparison</h2>
              <div className="h-[280px] flex items-end gap-3 px-8">
                {Array.from({ length: paywall.count }, (_, i) => (
                  <div key={i} className="flex-1 flex flex-col items-center gap-2">
                    <div
                      className="w-full rounded-t bg-primary/40"
                      style={{ height: `${100 + Math.random() * 160}px` }}
                    />
                    <div className="h-3 w-16 bg-muted rounded" />
                  </div>
                ))}
              </div>
              <div className="flex justify-between px-8 mt-2 text-xs text-muted-foreground">
                <span>Higher Skill Match →</span>
                <span>Higher Salary →</span>
              </div>
            </div>
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/60 backdrop-blur-[2px]">
              <div className="text-4xl mb-3">&#128274;</div>
              <h3 className="text-lg font-semibold">{paywall.message}</h3>
              <p className="text-sm text-muted-foreground mt-1 max-w-md text-center">
                See salary data, skill comparisons, learning plans, and personalized charts for each role.
              </p>
              <div className="flex items-center gap-3 mt-4">
                <Button onClick={handleUnlock} loading={unlocking} size="lg">
                  Unlock for {paywall.cost} Credit
                </Button>
                <Button variant="outline" size="lg" onClick={() => router.push("/billing")}>
                  Buy Credits
                </Button>
              </div>
              {walletBalance !== null && (
                <p className="text-xs text-muted-foreground mt-2">
                  Current balance: {walletBalance} credit{walletBalance !== 1 ? "s" : ""}
                </p>
              )}
            </div>
          </div>

          {Array.from({ length: Math.min(paywall.count, 3) }, (_, i) => (
            <div key={i} className="bg-card border rounded-lg p-6 relative overflow-hidden">
              <div className="blur-sm select-none pointer-events-none opacity-50 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="h-5 w-48 bg-muted rounded" />
                  <div className="h-4 w-24 bg-muted rounded" />
                </div>
                <div className="w-full bg-muted rounded-full h-2">
                  <div className="bg-primary/40 h-2 rounded-full" style={{ width: `${50 + i * 15}%` }} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="h-4 w-32 bg-muted rounded" />
                  <div className="h-4 w-28 bg-muted rounded" />
                  <div className="h-4 w-36 bg-muted rounded" />
                  <div className="h-4 w-24 bg-muted rounded" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="bg-destructive/10 border border-destructive rounded-lg p-4">
          <p className="text-destructive">{error}</p>
        </div>
      )}

      {/* Risk Score */}
      {risk && (
        <div className="bg-card border rounded-lg p-8 space-y-6">
          <div className="text-center space-y-3">
            <h2 className="text-lg font-medium text-muted-foreground">
              Your AI Automation Risk
            </h2>
            <div className={`text-6xl font-bold ${riskColor(risk.automation_risk_score)}`}>
              {Math.round(risk.automation_risk_score)}%
            </div>
            <p className={`text-sm font-semibold ${riskColor(risk.automation_risk_score)}`}>
              {riskLabel(risk.automation_risk_score)}
            </p>
          </div>

          <div className="bg-muted/50 rounded-lg p-4 space-y-2">
            <div className="text-sm">
              <span className="font-medium">{risk.parsed_role}</span>
            </div>
            <div className="flex gap-4 text-xs text-muted-foreground">
              <span>{risk.years_experience} years experience</span>
              <span>{risk.industry}</span>
            </div>
          </div>

          <div className="text-sm text-muted-foreground space-y-1">
            <p>
              {risk.automation_risk_score < 30
                ? `Your role as a ${risk.parsed_role} has low exposure to AI automation. The creative, strategic, and interpersonal aspects of your work are difficult to automate.`
                : risk.automation_risk_score < 60
                ? `Your role has moderate automation exposure. Some routine tasks can be automated, but core responsibilities still require human judgment. Consider upskilling in the areas below.`
                : `Your role has significant automation exposure. Many routine tasks in this field are already being automated. A career pivot could help you move into more resilient territory.`}
            </p>
          </div>

          {risk.resistant_abilities && risk.resistant_abilities.length > 0 && (
            <div>
              <h3 className="text-sm font-medium mb-2">Your automation-resistant strengths</h3>
              <p className="text-xs text-muted-foreground mb-2">
                These abilities are hard for AI to replicate and help protect your career:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {risk.resistant_abilities.map((ability, i) => (
                  <span
                    key={i}
                    className="text-xs bg-green-500/10 text-green-400 border border-green-500/20 px-2 py-0.5 rounded-full"
                  >
                    {ability}
                  </span>
                ))}
              </div>
            </div>
          )}

          {risk.task_breakdown.length > 0 && (
            <div>
              <h3 className="text-sm font-medium mb-1">Task-by-task automation risk</h3>
              <p className="text-xs text-muted-foreground mb-3">
                How likely each part of your daily work is to be automated, based on federal labor data.
                <span className="text-green-400 ml-1">Green = safe</span>,{" "}
                <span className="text-yellow-400">yellow = at risk</span>,{" "}
                <span className="text-red-400">red = high risk</span>.
              </p>
              <TaskRiskBars tasks={risk.task_breakdown} />
            </div>
          )}

          <p className="text-xs text-muted-foreground text-center pt-2 border-t border-muted">
            Based on U.S. Department of Labor occupational data and academic automation research
          </p>
        </div>
      )}

      {/* Pivot Comparison Chart */}
      {pivots.length > 0 && (
        <div className="bg-card border rounded-lg p-6">
          <h2 className="text-lg font-medium mb-4">Pivot Role Comparison</h2>
          <p className="text-sm text-muted-foreground mb-4">
            Bubble size = projected annual job openings. Color = AI risk (green=low, red=high).
          </p>
          <PivotComparisonScatter pivots={pivots} />
        </div>
      )}

      {/* Pivot Roles */}
      {pivots.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">Recommended Pivot Roles</h2>
          {pivots.map((pivot, i) => (
            <div key={i} className="bg-card border rounded-lg p-6 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold">
                  #{i + 1} {pivot.role}
                  {pivot.soc_code && (
                    <span
                      className="text-xs text-muted-foreground ml-2 font-normal border-b border-dotted border-muted-foreground cursor-help"
                      title="Standard Occupational Classification code — used by the U.S. Department of Labor to categorize jobs"
                    >
                      {pivot.soc_code}
                    </span>
                  )}
                </h3>
                <span className="text-sm text-muted-foreground">
                  {Math.round(pivot.skill_overlap_pct)}% skill match
                </span>
              </div>

              <div className="w-full bg-muted rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full transition-all duration-700"
                  style={{ width: `${pivot.skill_overlap_pct}%` }}
                />
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                {pivot.salary_range && (
                  <div>
                    <span className="text-muted-foreground">Salary: </span>
                    ${(pivot.salary_range.min / 1000).toFixed(0)}K - $
                    {(pivot.salary_range.max / 1000).toFixed(0)}K
                    <span className="text-xs text-muted-foreground ml-1">
                      (median ${(pivot.salary_range.median / 1000).toFixed(0)}K)
                    </span>
                  </div>
                )}
                <div>
                  <span className="text-muted-foreground">AI Risk: </span>
                  <span className={riskColor(pivot.ai_risk_pct)}>
                    {Math.round(pivot.ai_risk_pct)}%
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">Openings: </span>
                  {pivot.market_demand.toLocaleString()}/yr
                </div>
                <div>
                  <span className="text-muted-foreground">Time to pivot: </span>
                  ~{pivot.time_to_pivot_weeks} weeks
                </div>
                {pivot.growth_rate && (
                  <div>
                    <span className="text-muted-foreground">Growth: </span>
                    {pivot.growth_rate}
                  </div>
                )}
                {pivot.entry_education && (
                  <div>
                    <span className="text-muted-foreground">Education: </span>
                    {pivot.entry_education}
                  </div>
                )}
              </div>

              {pivot.missing_skills.length > 0 && (
                <div className="text-sm">
                  <span className="text-muted-foreground">Skills gap: </span>
                  {pivot.missing_skills.join(", ")}
                </div>
              )}

              {pivot.skill_comparison && (
                <div className="mt-2">
                  <button
                    onClick={() => setExpandedRadar(expandedRadar === i ? null : i)}
                    className="text-sm text-primary hover:underline cursor-pointer"
                  >
                    {expandedRadar === i ? "Hide Skill Comparison" : "View Skill Comparison"}
                  </button>
                  {expandedRadar === i && (
                    <div className="mt-3 flex justify-center">
                      <SkillGapRadar comparison={pivot.skill_comparison} roleName={pivot.role} />
                    </div>
                  )}
                </div>
              )}

              {pivot.learning_plan.length > 0 && (
                <details className="text-sm">
                  <summary className="cursor-pointer text-primary hover:underline">
                    View Learning Plan
                  </summary>
                  <div className="mt-2 space-y-2 pl-4">
                    {pivot.learning_plan.map((week: LearningWeek, j: number) => (
                      <div key={j} className="border-l-2 border-muted pl-3">
                        <p className="font-medium">
                          Week {week.week}: {week.topic}
                        </p>
                        {week.resources?.map((r: LearningResource, k: number) => (
                          <p key={k} className="text-muted-foreground">
                            {r.name} · {r.hours}hrs · {r.cost}
                          </p>
                        ))}
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
