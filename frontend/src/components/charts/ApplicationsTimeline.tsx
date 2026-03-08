"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface ApplicationsTimelineProps {
  sessions: Array<{
    created_at: string;
    applications_submitted: number;
    applications_failed: number;
  }>;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function ApplicationsTimeline({
  sessions,
}: ApplicationsTimelineProps) {
  if (!sessions || sessions.length < 2) return null;

  const grouped = new Map<string, number>();

  for (const s of sessions) {
    if (!s.created_at) continue;
    const key = formatDate(s.created_at);
    grouped.set(key, (grouped.get(key) ?? 0) + (s.applications_submitted ?? 0));
  }

  const data = Array.from(grouped.entries()).map(([date, count]) => ({
    date,
    count,
  }));

  if (data.length < 2) return null;

  const gradientId = "timelineFill";

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: -20 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(160, 84%, 39%)" stopOpacity={0.4} />
            <stop offset="95%" stopColor="hsl(160, 84%, 39%)" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="date"
          tick={{ fontSize: 12, fill: "hsl(0, 0%, 55%)" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          allowDecimals={false}
          tick={{ fontSize: 12, fill: "hsl(0, 0%, 55%)" }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{
            background: "hsl(0, 0%, 12%)",
            border: "1px solid hsl(0, 0%, 22%)",
            borderRadius: 8,
            fontSize: 13,
            color: "hsl(0, 0%, 90%)",
          }}
          formatter={((value: number) => [value, "Submitted"]) as never}
          labelFormatter={((label: string) => label) as never}
        />
        <Area
          type="monotone"
          dataKey="count"
          stroke="hsl(160, 84%, 39%)"
          strokeWidth={2}
          fill={`url(#${gradientId})`}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
