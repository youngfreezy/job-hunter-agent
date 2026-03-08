"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { API_BASE } from "@/lib/api";
import TaskRiskBars from "@/components/charts/TaskRiskBars";
import PivotComparisonScatter from "@/components/charts/PivotComparisonScatter";

interface TaskBreakdown {
  task: string;
  risk_pct: number;
}

interface LearningResource {
  name: string;
  hours: number;
  cost: string;
}

interface LearningWeek {
  week: number;
  topic: string;
  resources?: LearningResource[];
}

interface PivotRole {
  role: string;
  skill_overlap_pct: number;
  salary_range: { min: number; max: number; median: number };
  market_demand: number;
  ai_risk_pct: number;
  missing_skills: string[];
  learning_plan: LearningWeek[];
  time_to_pivot_weeks: number;
}

interface RiskAssessment {
  automation_risk_score: number;
  task_breakdown: TaskBreakdown[];
  parsed_role: string;
  parsed_skills: string[];
  years_experience: number;
  industry: string;
}

export default function PivotResultPage() {
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState("connecting");
  const [statusMessage, setStatusMessage] = useState("Connecting...");
  const [risk, setRisk] = useState<RiskAssessment | null>(null);
  const [pivots, setPivots] = useState<PivotRole[]>([]);
  const [error, setError] = useState<string | null>(null);

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

      {/* Status */}
      {status !== "completed" && !error && (
        <div className="bg-card border rounded-lg p-6 text-center">
          <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-muted-foreground">{statusMessage}</p>
        </div>
      )}

      {error && (
        <div className="bg-destructive/10 border border-destructive rounded-lg p-4">
          <p className="text-destructive">{error}</p>
        </div>
      )}

      {/* Risk Score */}
      {risk && (
        <div className="bg-card border rounded-lg p-8 text-center space-y-4">
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
          <p className="text-muted-foreground">
            {risk.parsed_role} · {risk.years_experience} years · {risk.industry}
          </p>

          {/* Task Breakdown */}
          <div className="mt-6 text-left max-w-lg mx-auto">
            <h3 className="font-medium text-sm mb-2">Task Automation Risk</h3>
            <TaskRiskBars tasks={risk.task_breakdown} />
          </div>

          <p className="text-xs text-muted-foreground mt-4">
            Powered by O*NET + BLS data
          </p>
        </div>
      )}

      {/* Pivot Comparison Chart */}
      {pivots.length > 0 && (
        <div className="bg-card border rounded-lg p-6">
          <h2 className="text-lg font-medium mb-4">Pivot Role Comparison</h2>
          <p className="text-sm text-muted-foreground mb-4">Bubble size = market demand. Color = AI risk (green=low, red=high).</p>
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
                </h3>
                <span className="text-sm text-muted-foreground">
                  {Math.round(pivot.skill_overlap_pct)}% skill match
                </span>
              </div>

              <div className="w-full bg-muted rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full"
                  style={{ width: `${pivot.skill_overlap_pct}%` }}
                />
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">Salary: </span>
                  ${(pivot.salary_range.min / 1000).toFixed(0)}K - $
                  {(pivot.salary_range.max / 1000).toFixed(0)}K
                </div>
                <div>
                  <span className="text-muted-foreground">AI Risk: </span>
                  <span className={riskColor(pivot.ai_risk_pct)}>
                    {Math.round(pivot.ai_risk_pct)}%
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">Openings: </span>
                  {pivot.market_demand.toLocaleString()}
                </div>
                <div>
                  <span className="text-muted-foreground">Time to pivot: </span>
                  ~{pivot.time_to_pivot_weeks} weeks
                </div>
              </div>

              {pivot.missing_skills.length > 0 && (
                <div className="text-sm">
                  <span className="text-muted-foreground">Skills gap: </span>
                  {pivot.missing_skills.join(", ")}
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
                            📚 {r.name} · {r.hours}hrs · {r.cost}
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
