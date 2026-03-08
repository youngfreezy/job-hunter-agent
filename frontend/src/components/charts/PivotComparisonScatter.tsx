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

interface PivotComparisonScatterProps {
  pivots: Array<{
    role: string;
    skill_overlap_pct: number;
    salary_range: { min: number; max: number; median: number };
    market_demand: number;
    ai_risk_pct: number;
  }>;
}

function aiRiskColor(pct: number): string {
  if (pct > 70) return "#ef4444";
  if (pct >= 40) return "#eab308";
  return "#22c55e";
}

interface PivotDatum {
  role: string;
  skillOverlap: number;
  salaryMedian: number;
  salaryMin: number;
  salaryMax: number;
  demand: number;
  aiRisk: number;
}

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: PivotDatum }>;
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
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{d.role}</div>
      <div>Skill Overlap: {d.skillOverlap}%</div>
      <div>
        Salary: ${d.salaryMin}K &ndash; ${d.salaryMax}K (median ${d.salaryMedian}K)
      </div>
      <div>Market Demand: {d.demand}</div>
      <div>AI Risk: {d.aiRisk}%</div>
    </div>
  );
}

export default function PivotComparisonScatter({
  pivots,
}: PivotComparisonScatterProps) {
  if (!pivots || pivots.length === 0) return null;

  const data: PivotDatum[] = pivots.map((p) => ({
    role: p.role,
    skillOverlap: p.skill_overlap_pct,
    salaryMedian: p.salary_range.median,
    salaryMin: p.salary_range.min,
    salaryMax: p.salary_range.max,
    demand: p.market_demand,
    aiRisk: p.ai_risk_pct,
  }));

  const demandValues = data.map((d) => d.demand);
  const demandMin = Math.min(...demandValues);
  const demandMax = Math.max(...demandValues);

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ScatterChart margin={{ top: 10, right: 20, bottom: 24, left: 10 }}>
        <XAxis
          type="number"
          dataKey="skillOverlap"
          domain={[0, 100]}
          tick={{ fill: "#a1a1aa", fontSize: 12 }}
          label={{
            value: "Skill Overlap %",
            position: "insideBottom",
            offset: -10,
            fill: "#a1a1aa",
            fontSize: 12,
          }}
        />
        <YAxis
          type="number"
          dataKey="salaryMedian"
          tick={{ fill: "#a1a1aa", fontSize: 12 }}
          tickFormatter={(v: number) => `$${v}K`}
          label={{
            value: "Median Salary ($K)",
            angle: -90,
            position: "insideLeft",
            offset: 10,
            fill: "#a1a1aa",
            fontSize: 12,
          }}
        />
        <ZAxis
          type="number"
          dataKey="demand"
          domain={[demandMin, demandMax]}
          range={[60, 400]}
        />
        <Tooltip content={<CustomTooltip />} />
        <Scatter data={data}>
          {data.map((entry, idx) => (
            <Cell key={idx} fill={aiRiskColor(entry.aiRisk)} fillOpacity={0.85} />
          ))}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}
