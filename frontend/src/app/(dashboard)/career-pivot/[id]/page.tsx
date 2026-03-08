"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { API_BASE } from "@/lib/api";
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

export default function PivotResultPage() {
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState("connecting");
  const [statusMessage, setStatusMessage] = useState("Connecting...");
  const [risk, setRisk] = useState<RiskAssessment | null>(null);
  const [pivots, setPivots] = useState<PivotRole[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expandedRadar, setExpandedRadar] = useState<number | null>(null);

  useEffect(() => {
    let es: EventSource | null = null;

    async function connect() {
      const url = `${API_BASE}/api/career-pivot/${id}/stream`;
      es = new EventSource(url);

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
      });

      es.addEventListener("done", () => {
        setStatus("completed");
        setStatusMessage("Analysis complete!");
        es?.close();
      });

      es.addEventListener("error", (e) => {
        if (e instanceof MessageEvent) {
          setError(JSON.parse(e.data).message);
        }
        es?.close();
      });

      es.onerror = () => {
        es?.close();
      };
    }

    connect();
    return () => es?.close();
  }, [id]);

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

      {/* Secondary loading — show when risk is loaded but pivots still pending */}
      {risk && pivots.length === 0 && status !== "completed" && !error && (
        <div className="bg-card border rounded-lg p-4 flex items-center gap-3">
          <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full" />
          <p className="text-sm text-muted-foreground">Finding recommended pivot roles...</p>
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
          {/* Score header */}
          <div className="text-center space-y-3">
            <h2 className="text-lg font-medium text-muted-foreground">
              Your AI Automation Risk
            </h2>
            <div
              className={`text-6xl font-bold ${riskColor(risk.automation_risk_score)}`}
            >
              {Math.round(risk.automation_risk_score)}%
            </div>
            <p
              className={`text-sm font-semibold ${riskColor(risk.automation_risk_score)}`}
            >
              {riskLabel(risk.automation_risk_score)}
            </p>
          </div>

          {/* Role context */}
          <div className="bg-muted/50 rounded-lg p-4 space-y-2">
            <div className="text-sm">
              <span className="font-medium">{risk.parsed_role}</span>
            </div>
            <div className="flex gap-4 text-xs text-muted-foreground">
              <span>{risk.years_experience} years experience</span>
              <span>{risk.industry}</span>
            </div>
          </div>

          {/* What this means */}
          <div className="text-sm text-muted-foreground space-y-1">
            <p>
              {risk.automation_risk_score < 30
                ? `Your role as a ${risk.parsed_role} has low exposure to AI automation. The creative, strategic, and interpersonal aspects of your work are difficult to automate.`
                : risk.automation_risk_score < 60
                ? `Your role has moderate automation exposure. Some routine tasks can be automated, but core responsibilities still require human judgment. Consider upskilling in the areas below.`
                : `Your role has significant automation exposure. Many routine tasks in this field are already being automated. A career pivot could help you move into more resilient territory.`}
            </p>
          </div>

          {/* Automation-Resistant Abilities */}
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

          {/* Task Breakdown */}
          {risk.task_breakdown.length > 0 && (
            <div>
              <h3 className="text-sm font-medium mb-1">
                Task-by-task automation risk
              </h3>
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
                <div>
                  <span className="text-muted-foreground">Salary: </span>
                  ${(pivot.salary_range.min / 1000).toFixed(0)}K - $
                  {(pivot.salary_range.max / 1000).toFixed(0)}K
                  <span className="text-xs text-muted-foreground ml-1">
                    (median ${(pivot.salary_range.median / 1000).toFixed(0)}K)
                  </span>
                </div>
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

              {/* Skill Gap Radar */}
              {pivot.skill_comparison && (
                <div className="mt-2">
                  <button
                    onClick={() =>
                      setExpandedRadar(expandedRadar === i ? null : i)
                    }
                    className="text-sm text-primary hover:underline cursor-pointer"
                  >
                    {expandedRadar === i
                      ? "Hide Skill Comparison"
                      : "View Skill Comparison"}
                  </button>
                  {expandedRadar === i && (
                    <div className="mt-3 flex justify-center">
                      <SkillGapRadar
                        comparison={pivot.skill_comparison}
                        roleName={pivot.role}
                      />
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
