// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";

interface JobComparisonChartProps {
  jobs: Array<{
    title: string;
    company: string;
    score_breakdown?: Record<string, number>;
  }>;
}

const PALETTE = ["#6366f1", "#06b6d4", "#f59e0b", "#ec4899", "#10b981"];

export default function JobComparisonChart({ jobs }: JobComparisonChartProps) {
  const withBreakdown = (jobs ?? [])
    .filter((j) => j.score_breakdown && Object.keys(j.score_breakdown).length > 0)
    .slice(0, 5);

  if (withBreakdown.length === 0) return null;

  // Collect all unique breakdown keys across jobs
  const allKeys = Array.from(
    new Set(withBreakdown.flatMap((j) => Object.keys(j.score_breakdown!)))
  );

  // Build data: one entry per breakdown dimension, with each job as a field
  const data = allKeys.map((key) => {
    const entry: Record<string, string | number> = {
      dimension: key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    };
    withBreakdown.forEach((job) => {
      entry[job.company] = job.score_breakdown?.[key] ?? 0;
    });
    return entry;
  });

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} barCategoryGap="25%">
        <XAxis
          dataKey="dimension"
          tick={{ fill: "#a1a1aa", fontSize: 11 }}
          axisLine={{ stroke: "#555" }}
          tickLine={false}
          interval={0}
          angle={-20}
          textAnchor="end"
          height={50}
        />
        <YAxis
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
        />
        <Legend wrapperStyle={{ fontSize: 12, color: "#a1a1aa" }} />
        {withBreakdown.map((job, i) => (
          <Bar
            key={job.company}
            dataKey={job.company}
            fill={PALETTE[i % PALETTE.length]}
            radius={[3, 3, 0, 0]}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
