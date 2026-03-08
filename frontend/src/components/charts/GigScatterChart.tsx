"use client";

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface GigScatterChartProps {
  gigs: Array<{
    id: string;
    title: string;
    platform: string;
    match_score: number;
    budget_min: number;
    budget_max: number;
    proposals_count: number;
  }>;
}

const PLATFORM_COLORS: Record<string, string> = {
  Upwork: "#22c55e",
  LinkedIn: "#3b82f6",
  Fiverr: "#f97316",
};

function platformColor(platform: string): string {
  return PLATFORM_COLORS[platform] ?? "#9ca3af";
}

interface GigDatum {
  id: string;
  title: string;
  platform: string;
  matchScore: number;
  budgetMid: number;
  budgetMin: number;
  budgetMax: number;
  proposals: number;
  competitionSize: number;
}

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: GigDatum }>;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div
      style={{
        backgroundColor: "#1f2937",
        border: "1px solid #374151",
        borderRadius: 6,
        padding: "8px 12px",
        color: "#e5e7eb",
        fontSize: 13,
        lineHeight: 1.5,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{d.title}</div>
      <div>Platform: {d.platform}</div>
      <div>Match Score: {d.matchScore}%</div>
      <div>
        Budget: ${d.budgetMin.toLocaleString()} &ndash; $
        {d.budgetMax.toLocaleString()}
      </div>
      <div>Proposals: {d.proposals}</div>
    </div>
  );
}

export default function GigScatterChart({ gigs }: GigScatterChartProps) {
  if (!gigs || gigs.length < 3) return null;

  const data: GigDatum[] = gigs.map((g) => ({
    id: g.id,
    title: g.title,
    platform: g.platform,
    matchScore: g.match_score,
    budgetMid: (g.budget_min + g.budget_max) / 2,
    budgetMin: g.budget_min,
    budgetMax: g.budget_max,
    proposals: g.proposals_count,
    // Invert: fewer proposals -> larger dot
    competitionSize: Math.max(1, g.proposals_count),
  }));

  // Invert the ZAxis domain so fewer proposals = bigger bubble
  const proposalValues = data.map((d) => d.competitionSize);
  const pMin = Math.min(...proposalValues);
  const pMax = Math.max(...proposalValues);

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ScatterChart margin={{ top: 10, right: 20, bottom: 24, left: 10 }}>
        <XAxis
          type="number"
          dataKey="matchScore"
          domain={[0, 100]}
          tick={{ fill: "#a1a1aa", fontSize: 12 }}
          label={{
            value: "Match Score",
            position: "insideBottom",
            offset: -10,
            fill: "#a1a1aa",
            fontSize: 12,
          }}
        />
        <YAxis
          type="number"
          dataKey="budgetMid"
          tick={{ fill: "#a1a1aa", fontSize: 12 }}
          tickFormatter={(v: number) => `$${v.toLocaleString()}`}
          label={{
            value: "Budget ($)",
            angle: -90,
            position: "insideLeft",
            offset: 10,
            fill: "#a1a1aa",
            fontSize: 12,
          }}
        />
        <ZAxis
          type="number"
          dataKey="competitionSize"
          domain={[pMin, pMax]}
          range={[400, 60]}
        />
        <Tooltip content={<CustomTooltip />} />
        <Scatter data={data}>
          {data.map((entry, idx) => (
            <Cell
              key={entry.id ?? idx}
              fill={platformColor(entry.platform)}
              fillOpacity={0.85}
            />
          ))}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}
