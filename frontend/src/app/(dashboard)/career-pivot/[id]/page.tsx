// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { API_BASE, getAuthHeaders, getSSEToken, getWallet } from "@/lib/api";
import { Button } from "@/components/ui/button";
import TaskRiskBars from "@/components/charts/TaskRiskBars";
import PivotComparisonBars from "@/components/charts/PivotComparisonBars";
import SkillGapRadar from "@/components/charts/SkillGapRadar";
import SkillBridgeViz from "@/components/charts/SkillBridgeViz";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import type { LearningResource, LearningWeek, PivotRole, RiskAssessment, SkillBridge } from "@/lib/types/career-pivot";
import { riskColor, riskLabel } from "@/lib/utils";

export default function PivotResultPage() {
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState("connecting");
  const [, setStatusMessage] = useState("Connecting...");
  const [risk, setRisk] = useState<RiskAssessment | null>(null);
  const [pivots, setPivots] = useState<PivotRole[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expandedRadar, setExpandedRadar] = useState<number | null>(null);
  const [skillBridges, setSkillBridges] = useState<SkillBridge[]>([]);
  const [paywall, setPaywall] = useState<{ count: number; message: string; cost: number } | null>(null);
  const [unlocking, setUnlocking] = useState(false);
  const [walletBalance, setWalletBalance] = useState<number | null>(null);
  const router = useRouter();

  useEffect(() => {
    let es: EventSource | null = null;

    async function connect() {
      const token = await getSSEToken();
      const sep = token ? `?token=${encodeURIComponent(token)}` : "";
      es = new EventSource(`${API_BASE}/api/career-pivot/${id}/stream${sep}`);

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

      es.addEventListener("transferable_skills", (e) => {
        const data = JSON.parse(e.data);
        setSkillBridges(data.skill_bridges || []);
      });

      es.addEventListener("paywall", (e) => {
        const data = JSON.parse(e.data);
        setPaywall({ count: data.count, message: data.message, cost: data.cost });
        getWallet().then((w) => setWalletBalance(w.balance)).catch(() => {});
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

  async function handleUnlock() {
    setUnlocking(true);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_BASE}/api/career-pivot/${id}/unlock`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
      });
      if (res.status === 402) {
        router.push("/billing");
        return;
      }
      if (!res.ok) throw new Error("Unlock failed");
      // pivot_roles will arrive via SSE
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to unlock");
    } finally {
      setUnlocking(false);
    }
  }

  const isLoading = pivots.length === 0 && !paywall && status !== "completed" && !error;

  const statusText =
    status === "parsing_skills"
      ? "Parsing your resume..."
      : status === "researching_onet"
        ? "Researching your occupation..."
        : status === "assessing_risk"
          ? "Calculating your automation risk..."
          : status === "mapping_roles"
            ? "Finding adjacent roles you're qualified for..."
            : status === "mapping_cross_industry"
              ? "Mapping your skills to unexpected industries..."
              : "Starting your career analysis...";

  const progressWidth =
    status === "parsing_skills"
      ? "20%"
      : status === "researching_onet"
        ? "35%"
        : status === "assessing_risk"
          ? "50%"
          : status === "mapping_roles"
            ? "70%"
            : status === "mapping_cross_industry"
              ? "85%"
              : "10%";

  if (isLoading) {
    return (
      <div className="container mx-auto max-w-4xl p-6 space-y-6">
        <h1 className="text-2xl font-bold">Career Change Analysis</h1>

        <div className="space-y-6 animate-in fade-in duration-300">
          {/* Progress bar */}
          <div className="bg-card border rounded-lg p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full" />
              <p className="text-sm text-muted-foreground">{statusText}</p>
            </div>
            <div className="w-full bg-muted rounded-full h-1.5">
              <div
                className="bg-primary h-1.5 rounded-full animate-pulse transition-all duration-500"
                style={{ width: progressWidth }}
              />
            </div>
          </div>

          {/* Risk score — real data or skeleton */}
          {risk ? (
            <div className="bg-card border rounded-lg p-8 space-y-4">
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
            </div>
          ) : (
            <div className="bg-card border rounded-lg p-8 space-y-4">
              <div className="flex flex-col items-center space-y-3">
                <div className="h-4 w-40 bg-muted animate-pulse rounded" />
                <div className="h-14 w-20 bg-muted animate-pulse rounded" />
                <div className="h-3 w-24 bg-muted animate-pulse rounded" />
              </div>
              <div className="bg-muted/50 rounded-lg p-4 space-y-2">
                <div className="h-4 w-48 bg-muted animate-pulse rounded" />
                <div className="h-3 w-32 bg-muted animate-pulse rounded" />
              </div>
            </div>
          )}

          {/* Career comparison skeleton */}
          <div className="bg-card border rounded-lg p-6 space-y-3">
            <div className="h-5 w-40 bg-muted animate-pulse rounded" />
            <div className="h-3 w-64 bg-muted animate-pulse rounded" />
            <div className="h-[200px] flex items-end gap-3 pt-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-2">
                  <div
                    className="w-full rounded-t bg-muted animate-pulse"
                    style={{ height: `${80 + i * 30}px` }}
                  />
                  <div className="h-3 w-16 bg-muted animate-pulse rounded" />
                </div>
              ))}
            </div>
          </div>

          {/* Role card skeletons */}
          {[1, 2].map((i) => (
            <div key={i} className="bg-card border rounded-lg p-6 space-y-3">
              <div className="flex items-center justify-between">
                <div className="h-5 w-48 bg-muted animate-pulse rounded" />
                <div className="h-4 w-24 bg-muted animate-pulse rounded" />
              </div>
              <div className="w-full bg-muted rounded-full h-2">
                <div
                  className="bg-muted animate-pulse h-2 rounded-full"
                  style={{ width: `${50 + i * 15}%` }}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="h-4 w-32 bg-muted animate-pulse rounded" />
                <div className="h-4 w-28 bg-muted animate-pulse rounded" />
                <div className="h-4 w-36 bg-muted animate-pulse rounded" />
                <div className="h-4 w-24 bg-muted animate-pulse rounded" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-4xl p-6 space-y-8">
      <h1 className="text-2xl font-bold">Career Change Analysis</h1>

      {/* Paywall — unlock pivot roles with blurred chart preview */}
      {paywall && pivots.length === 0 && (
        <div className="space-y-4">
          {/* Blurred chart preview */}
          <div className="bg-card border rounded-lg p-6 relative overflow-hidden">
            <div className="blur-sm select-none pointer-events-none opacity-60">
              <h2 className="text-lg font-medium mb-2">Career Comparison</h2>
              <div className="h-[280px] flex items-end gap-3 px-8">
                {Array.from({ length: paywall.count }, (_, i) => (
                  <div key={i} className="flex-1 flex flex-col items-center gap-2">
                    <div
                      className="w-full rounded-t bg-primary/40"
                      style={{ height: `${120 + i * 40}px` }}
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

          {/* Blurred role cards preview */}
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
                : `Your role has significant automation exposure. Many routine tasks in this field are already being automated. A career change could help you move into more resilient territory.`}
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

      {/* Pivot Results — Tabs */}
      {pivots.length > 0 && (
        <Tabs defaultValue="pivots" className="space-y-4">
          <TabsList>
            <TabsTrigger value="pivots">Recommended Careers</TabsTrigger>
            <TabsTrigger value="bridges" disabled={skillBridges.length === 0}>
              Skills to New Industries
              {skillBridges.length === 0 && status !== "completed" && (
                <span className="ml-1.5 inline-block h-3 w-3 animate-spin rounded-full border border-current border-t-transparent" />
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="pivots" className="space-y-4">
            {/* Comparison Chart */}
            <div className="bg-card border rounded-lg p-6">
              <h2 className="text-lg font-medium mb-2">Career Comparison</h2>
              <p className="text-sm text-muted-foreground mb-4">
                Blue = skill match, green = AI safety (100 - risk), amber = relative salary.
              </p>
              <PivotComparisonBars pivots={pivots} />
            </div>

            {/* Role Cards */}
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
                  <span className="text-muted-foreground">Transition time:</span>
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
          </TabsContent>

          <TabsContent value="bridges" className="space-y-4">
            <div className="bg-card border rounded-lg p-6">
              <h2 className="text-lg font-medium mb-2">Your Skills in New Industries</h2>
              <p className="text-sm text-muted-foreground mb-4">
                Select a skill to see unexpected career paths where it transfers — across industries and collar types.
              </p>
              {skillBridges.length > 0 ? (
                <SkillBridgeViz bridges={skillBridges} />
              ) : (
                <div className="flex items-center gap-3 py-8 justify-center">
                  <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full" />
                  <p className="text-sm text-muted-foreground">Mapping transferable skills...</p>
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
