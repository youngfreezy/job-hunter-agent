"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface ScoreDistributionProps {
  scores: number[];
}

const BINS = [
  { label: "0-20", min: 0, max: 20, color: "#ef4444" },
  { label: "21-40", min: 21, max: 40, color: "#f97316" },
  { label: "41-60", min: 41, max: 60, color: "#eab308" },
  { label: "61-80", min: 61, max: 80, color: "#84cc16" },
  { label: "81-100", min: 81, max: 100, color: "#22c55e" },
];

export default function ScoreDistribution({ scores }: ScoreDistributionProps) {
  if (!scores || scores.length === 0) return null;

  const data = BINS.map((bin) => ({
    range: bin.label,
    count: scores.filter((s) => s >= bin.min && s <= bin.max).length,
    color: bin.color,
  }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} barCategoryGap="20%">
        <XAxis
          dataKey="range"
          tick={{ fill: "#a1a1aa", fontSize: 12 }}
          axisLine={{ stroke: "#555" }}
          tickLine={false}
        />
        <YAxis
          allowDecimals={false}
          tick={{ fill: "#a1a1aa", fontSize: 12 }}
          axisLine={{ stroke: "#555" }}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#1f2937",
            border: "1px solid #374151",
            borderRadius: 6,
            color: "#e5e7eb",
          }}
          formatter={(value) => [`${value}`, "Jobs"]}
        />
        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
