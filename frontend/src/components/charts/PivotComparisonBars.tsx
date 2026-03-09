// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";

interface PivotComparisonBarsProps {
  pivots: Array<{
    role: string;
    skill_overlap_pct: number;
    salary_range?: { min: number; max: number; median: number };
    ai_risk_pct: number;
  }>;
}

export default function PivotComparisonBars({ pivots }: PivotComparisonBarsProps) {
  if (!pivots || pivots.length === 0) return null;

  const maxMedian = Math.max(...pivots.map((p) => p.salary_range?.median ?? 0));

  const data = pivots.map((p) => {
    const median = p.salary_range?.median ?? 0;
    return {
      role: p.role.length > 25 ? p.role.slice(0, 23) + "…" : p.role,
      fullRole: p.role,
      "Skill Match": Math.round(p.skill_overlap_pct),
      "AI Safety": Math.round(100 - p.ai_risk_pct),
      Salary: maxMedian > 0 ? Math.round((median / maxMedian) * 100) : 0,
      _salaryRaw: p.salary_range,
      _aiRisk: p.ai_risk_pct,
    };
  });

  return (
    <ResponsiveContainer width="100%" height={Math.max(200, pivots.length * 60 + 40)}>
      <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
        <XAxis
          type="number"
          domain={[0, 100]}
          tick={{ fill: "#a1a1aa", fontSize: 11 }}
          axisLine={{ stroke: "#374151" }}
          tickLine={false}
          tickFormatter={(v) => `${v}%`}
        />
        <YAxis
          type="category"
          dataKey="role"
          width={150}
          tick={{ fill: "#d1d5db", fontSize: 12 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#1f2937",
            border: "1px solid #374151",
            borderRadius: 6,
            color: "#e5e7eb",
          }}
          formatter={(value, name, props) => {
            const payload = (props as { payload?: Record<string, unknown> })?.payload;
            if (name === "Salary" && payload?._salaryRaw) {
              const sr = payload._salaryRaw as { min: number; max: number; median: number };
              return [
                `$${(sr.min / 1000).toFixed(0)}K – $${(sr.max / 1000).toFixed(0)}K (median $${(
                  sr.median / 1000
                ).toFixed(0)}K)`,
                "Salary",
              ];
            }
            if (name === "AI Safety" && payload) {
              return [`${value}% (AI Risk: ${payload._aiRisk}%)`, "AI Safety"];
            }
            return [`${value}%`, String(name)];
          }}
          labelFormatter={(label) => {
            const item = data.find((d) => d.role === label);
            return item?.fullRole ?? label;
          }}
        />
        <Legend wrapperStyle={{ color: "#a1a1aa", fontSize: 12 }} />
        <Bar dataKey="Skill Match" fill="#3b82f6" radius={[0, 4, 4, 0]} barSize={14} />
        <Bar dataKey="AI Safety" fill="#22c55e" radius={[0, 4, 4, 0]} barSize={14} />
        <Bar dataKey="Salary" fill="#f59e0b" radius={[0, 4, 4, 0]} barSize={14} />
      </BarChart>
    </ResponsiveContainer>
  );
}
