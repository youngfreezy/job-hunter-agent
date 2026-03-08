// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  Radar,
  ResponsiveContainer,
} from "recharts";

import type { ResumeScore } from "@/lib/api";

interface ResumeScoreRadarProps {
  scores: ResumeScore | null | undefined;
}

const DIMENSION_LABELS: Record<string, string> = {
  keyword_density: "Keywords",
  impact_metrics: "Impact",
  ats_compatibility: "ATS",
  readability: "Readability",
  formatting: "Format",
  feedback: "Feedback",
};

const NUMERIC_KEYS: (keyof ResumeScore)[] = [
  "keyword_density",
  "impact_metrics",
  "ats_compatibility",
  "readability",
  "formatting",
];

export default function ResumeScoreRadar({ scores }: ResumeScoreRadarProps) {
  if (!scores) return null;

  const data = NUMERIC_KEYS.map((key) => ({
    dimension: DIMENSION_LABELS[key] ?? key,
    value: Math.min(100, Math.max(0, scores[key] as number)),
  }));

  return (
    <ResponsiveContainer width="100%" height={250}>
      <RadarChart data={data} cx="50%" cy="50%" outerRadius="60%">
        <PolarGrid stroke="#555" />
        <PolarAngleAxis
          dataKey="dimension"
          tick={{ fill: "#a1a1aa", fontSize: 11 }}
        />
        <Radar
          name="Score"
          dataKey="value"
          stroke="#6366f1"
          fill="#6366f1"
          fillOpacity={0.3}
          dot={{ r: 3, fill: "#6366f1" }}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}
