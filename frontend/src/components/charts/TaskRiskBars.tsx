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

interface TaskRiskBarsProps {
  tasks: Array<{ task: string; risk_pct: number }>;
}

function riskColor(pct: number): string {
  if (pct > 70) return "#ef4444";
  if (pct >= 40) return "#eab308";
  return "#22c55e";
}

function truncate(str: string, max: number): string {
  return str.length > max ? str.slice(0, max - 1) + "\u2026" : str;
}

export default function TaskRiskBars({ tasks }: TaskRiskBarsProps) {
  if (!tasks || tasks.length === 0) return null;

  const data = tasks.map((t) => ({
    name: truncate(t.task, 28),
    fullName: t.task,
    risk: Math.min(100, Math.max(0, t.risk_pct)),
  }));

  const chartHeight = tasks.length * 40 + 40;

  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20 }}>
        <XAxis
          type="number"
          domain={[0, 100]}
          tick={{ fill: "#a1a1aa", fontSize: 12 }}
          tickFormatter={(v: number) => `${v}%`}
          label={{
            value: "Automation Risk %",
            position: "insideBottom",
            offset: -2,
            fill: "#a1a1aa",
            fontSize: 12,
          }}
        />
        <YAxis
          type="category"
          dataKey="name"
          width={160}
          tick={{ fill: "#a1a1aa", fontSize: 12 }}
        />
        <Tooltip
          cursor={{ fill: "rgba(255,255,255,0.05)" }}
          contentStyle={{
            backgroundColor: "#1f2937",
            border: "1px solid #374151",
            borderRadius: 6,
            color: "#e5e7eb",
            fontSize: 13,
          }}
          formatter={(value) => [`${value}%`, "Risk"]}
          labelFormatter={(_label, payload) => {
            const item = payload?.[0] as { payload?: { fullName?: string } } | undefined;
            return item?.payload?.fullName ?? String(_label);
          }}
        />
        <Bar dataKey="risk" radius={[0, 4, 4, 0]} barSize={20}>
          {data.map((entry, idx) => (
            <Cell key={idx} fill={riskColor(entry.risk)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
