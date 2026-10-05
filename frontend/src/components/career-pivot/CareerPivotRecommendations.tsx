// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import PivotComparisonBars from "@/components/charts/PivotComparisonBars";
import SkillBridgeViz from "@/components/charts/SkillBridgeViz";
import SkillGapRadar from "@/components/charts/SkillGapRadar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type {
  LearningResource,
  LearningWeek,
  PivotRole,
  SkillBridge
} from "@/lib/types/career-pivot";
import { riskColor } from "@/lib/utils";

type Props = {
  pivots: PivotRole[];
  skillBridges: SkillBridge[];
  status: string;
  expandedRadar: number | null;
  setExpandedRadar: (index: number | null) => void;
};

export function CareerPivotRecommendations({ pivots, skillBridges, status, expandedRadar, setExpandedRadar }: Props) {
  return <>
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
                    <span className="text-muted-foreground">Salary: </span>$
                    {(pivot.salary_range.min / 1000).toFixed(0)}K - $
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
                  <span className="text-muted-foreground">Transition time:</span>~
                  {pivot.time_to_pivot_weeks} weeks
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
        </TabsContent>

        <TabsContent value="bridges" className="space-y-4">
          <div className="bg-card border rounded-lg p-6">
            <h2 className="text-lg font-medium mb-2">Your Skills in New Industries</h2>
            <p className="text-sm text-muted-foreground mb-4">
              Select a skill to see unexpected career paths where it transfers — across industries
              and collar types.
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
  </>;
}
