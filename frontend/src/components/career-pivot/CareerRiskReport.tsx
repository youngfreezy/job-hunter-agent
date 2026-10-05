// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import TaskRiskBars from "@/components/charts/TaskRiskBars";
import type {
  RiskAssessment
} from "@/lib/types/career-pivot";
import { riskColor, riskLabel } from "@/lib/utils";

type Props = {
  risk: RiskAssessment | null;
};

export function CareerRiskReport({ risk }: Props) {
  return <>
    {/* Risk Score */}
    {risk && (
      <div className="bg-card border rounded-lg p-8 space-y-6">
        {/* Score header */}
        <div className="text-center space-y-3">
          <h2 className="text-lg font-medium text-muted-foreground">Your AI Automation Risk</h2>
          <div className={`text-6xl font-bold ${riskColor(risk.automation_risk_score)}`}>
            {Math.round(risk.automation_risk_score)}%
          </div>
          <p className={`text-sm font-semibold ${riskColor(risk.automation_risk_score)}`}>
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
            <h3 className="text-sm font-medium mb-1">Task-by-task automation risk</h3>
            <p className="text-xs text-muted-foreground mb-3">
              How likely each part of your daily work is to be automated, based on federal labor
              data.
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

  </>;
}
