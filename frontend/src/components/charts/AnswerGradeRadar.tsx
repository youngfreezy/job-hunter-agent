// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface GradeDimensions {
  relevance: number;
  specificity: number;
  star_structure: number;
  confidence: number;
}

interface AnswerGradeRadarProps {
  grade: GradeDimensions | null | undefined;
  averageGrades?: GradeDimensions | null;
}

const DIMENSION_LABELS: Record<string, string> = {
  relevance: "Relevance",
  specificity: "Specificity",
  star_structure: "STAR Structure",
  confidence: "Confidence",
};

const DIMENSIONS = ["relevance", "specificity", "star_structure", "confidence"] as const;

export default function AnswerGradeRadar({ grade, averageGrades }: AnswerGradeRadarProps) {
  if (!grade) return null;

  const data = DIMENSIONS.map((key) => ({
    dimension: DIMENSION_LABELS[key],
    current: Math.min(10, Math.max(0, grade[key] ?? 0)),
    ...(averageGrades ? { average: Math.min(10, Math.max(0, averageGrades[key] ?? 0)) } : {}),
  }));

  return (
    <ResponsiveContainer width="100%" height={250}>
      <RadarChart data={data} cx="50%" cy="50%" outerRadius="75%">
        <PolarGrid stroke="#555" />
        <PolarAngleAxis dataKey="dimension" tick={{ fill: "#a1a1aa", fontSize: 12 }} />
        <PolarRadiusAxis
          angle={90}
          domain={[0, 10]}
          tick={{ fill: "#71717a", fontSize: 10 }}
          axisLine={false}
        />
        <Radar
          name="This Answer"
          dataKey="current"
          stroke="#6366f1"
          fill="#6366f1"
          fillOpacity={0.3}
          dot={{ r: 3, fill: "#6366f1" }}
        />
        {averageGrades && (
          <Radar
            name="Average"
            dataKey="average"
            stroke="#71717a"
            fill="#71717a"
            fillOpacity={0.15}
            dot={{ r: 2, fill: "#71717a" }}
          />
        )}
        {averageGrades && <Legend wrapperStyle={{ fontSize: 12, color: "#a1a1aa" }} />}
      </RadarChart>
    </ResponsiveContainer>
  );
}
