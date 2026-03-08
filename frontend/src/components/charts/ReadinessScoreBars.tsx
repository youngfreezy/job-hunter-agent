"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Cell,
  LabelList,
  ResponsiveContainer,
} from "recharts";

interface ReadinessScoreBarsProps {
  categoryScores: Record<string, number> | null | undefined;
}

function getBarColor(score: number): string {
  if (score > 7) return "#22c55e";
  if (score >= 5) return "#eab308";
  return "#ef4444";
}

function formatLabel(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ReadinessScoreBars({ categoryScores }: ReadinessScoreBarsProps) {
  if (!categoryScores || Object.keys(categoryScores).length === 0) return null;

  const data = Object.entries(categoryScores).map(([key, value]) => ({
    category: formatLabel(key),
    score: Math.min(10, Math.max(0, value)),
  }));

  const chartHeight = data.length * 45 + 30;

  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 5, right: 40, bottom: 5, left: 10 }}
      >
        <XAxis
          type="number"
          domain={[0, 10]}
          tick={{ fill: "#a1a1aa", fontSize: 12 }}
          axisLine={{ stroke: "#555" }}
          tickLine={{ stroke: "#555" }}
        />
        <YAxis
          type="category"
          dataKey="category"
          width={120}
          tick={{ fill: "#a1a1aa", fontSize: 12 }}
          axisLine={false}
          tickLine={false}
        />
        <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={20}>
          {data.map((entry, index) => (
            <Cell key={index} fill={getBarColor(entry.score)} />
          ))}
          <LabelList
            dataKey="score"
            position="right"
            style={{ fill: "#a1a1aa", fontSize: 12, fontWeight: 500 }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
