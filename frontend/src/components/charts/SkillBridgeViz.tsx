"use client";

import { useState } from "react";

interface SkillBridgeTarget {
  industry: string;
  role: string;
  why: string;
  salary_range: { min: number; max: number; median: number };
  demand: string;
  growth_rate: string;
  collar: string;
  ai_resistant: boolean;
}

interface SkillBridge {
  your_skill: string;
  skill_category: string;
  transfers_to: SkillBridgeTarget[];
}

interface SkillBridgeVizProps {
  bridges: SkillBridge[];
}

const CATEGORY_COLORS: Record<string, string> = {
  Technical: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  Interpersonal: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  Cognitive: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  Physical: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
};

const COLLAR_STYLES: Record<string, { bg: string; label: string }> = {
  white: { bg: "bg-slate-500/20 text-slate-300", label: "White Collar" },
  blue: { bg: "bg-sky-500/20 text-sky-300", label: "Blue Collar" },
  pink: { bg: "bg-pink-500/20 text-pink-300", label: "Pink Collar" },
};

const DEMAND_COLORS: Record<string, string> = {
  High: "text-green-400",
  Medium: "text-yellow-400",
  Low: "text-red-400",
};

export default function SkillBridgeViz({ bridges }: SkillBridgeVizProps) {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [expandedWhy, setExpandedWhy] = useState<number | null>(null);

  if (!bridges || bridges.length === 0) return null;

  const selected = bridges[selectedIdx];

  return (
    <div className="space-y-4">
      {/* Skill pills */}
      <div className="flex flex-wrap gap-2">
        {bridges.map((bridge, i) => {
          const catClass =
            CATEGORY_COLORS[bridge.skill_category] ||
            "bg-muted text-muted-foreground border-muted";
          const isActive = i === selectedIdx;
          return (
            <button
              key={i}
              onClick={() => {
                setSelectedIdx(i);
                setExpandedWhy(null);
              }}
              className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-all cursor-pointer ${catClass} ${
                isActive ? "ring-2 ring-primary ring-offset-1 ring-offset-background" : "opacity-70 hover:opacity-100"
              }`}
            >
              {bridge.your_skill}
              <span className="ml-1.5 text-xs opacity-60">{bridge.skill_category}</span>
            </button>
          );
        })}
      </div>

      {/* Target role cards */}
      <div className="grid gap-3 sm:grid-cols-2">
        {selected.transfers_to.map((target, j) => {
          const collar = COLLAR_STYLES[target.collar] || COLLAR_STYLES.white;
          return (
            <div
              key={j}
              className="bg-card border rounded-lg p-4 space-y-2.5"
            >
              {/* Header row */}
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h4 className="font-semibold text-sm">{target.role}</h4>
                  <span className="text-xs text-muted-foreground">{target.industry}</span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${collar.bg}`}>
                    {collar.label}
                  </span>
                  {target.ai_resistant && (
                    <span
                      className="text-xs px-1.5 py-0.5 rounded bg-green-500/15 text-green-400"
                      title="AI-resistant role"
                    >
                      AI-Safe
                    </span>
                  )}
                </div>
              </div>

              {/* Stats */}
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                {target.salary_range && (
                  <span>
                    ${(target.salary_range.median / 1000).toFixed(0)}K median
                  </span>
                )}
                <span className={DEMAND_COLORS[target.demand] || ""}>
                  {target.demand} demand
                </span>
                {target.growth_rate && (
                  <span>{target.growth_rate}</span>
                )}
              </div>

              {/* Why this transfers */}
              <button
                onClick={() => setExpandedWhy(expandedWhy === j ? null : j)}
                className="text-xs text-primary hover:underline cursor-pointer"
              >
                {expandedWhy === j ? "Hide explanation" : "Why does this skill transfer?"}
              </button>
              {expandedWhy === j && (
                <p className="text-xs text-muted-foreground leading-relaxed bg-muted/40 rounded p-2.5">
                  {target.why}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
