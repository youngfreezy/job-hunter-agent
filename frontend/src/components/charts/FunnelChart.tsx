// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, LabelList } from "recharts";

interface FunnelChartProps {
  sessions: Array<{
    applications_submitted: number;
    applications_failed: number;
  }>;
}

export default function FunnelChart({ sessions }: FunnelChartProps) {
  if (!sessions || sessions.length === 0) return null;

  const totalSubmitted = sessions.reduce((sum, s) => sum + (s.applications_submitted ?? 0), 0);
  const totalFailed = sessions.reduce((sum, s) => sum + (s.applications_failed ?? 0), 0);

  if (totalSubmitted + totalFailed === 0) return null;

  const data = [
    {
      name: "Applications",
      submitted: totalSubmitted,
      failed: totalFailed,
    },
  ];

  return (
    <ResponsiveContainer width="100%" height={120}>
      <BarChart data={data} layout="vertical" margin={{ left: 0, right: 40 }}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="name" hide />
        <Bar dataKey="submitted" stackId="pipeline" fill="hsl(160, 84%, 39%)" radius={[4, 0, 0, 4]}>
          <LabelList
            dataKey="submitted"
            position="center"
            fill="#fff"
            fontWeight={600}
            fontSize={13}
            formatter={((v: number) => (v > 0 ? v : "")) as never}
          />
        </Bar>
        <Bar dataKey="failed" stackId="pipeline" fill="hsl(0, 84%, 60%)" radius={[0, 4, 4, 0]}>
          <LabelList
            dataKey="failed"
            position="center"
            fill="#fff"
            fontWeight={600}
            fontSize={13}
            formatter={((v: number) => (v > 0 ? v : "")) as never}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
