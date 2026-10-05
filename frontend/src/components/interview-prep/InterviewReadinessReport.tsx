// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import ReadinessScoreBars from "@/components/charts/ReadinessScoreBars";
import type {
  InterviewReport
} from "@/lib/types/interview-prep";

type Props = {
  report: InterviewReport | null;
};

export function InterviewReadinessReport({ report }: Props) {
  return <>
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

  </>;
}
