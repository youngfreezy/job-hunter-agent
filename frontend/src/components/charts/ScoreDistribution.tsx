// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

interface ScoreDistributionProps {
  scores: number[];
  statuses?: string[];
}

const STATUS_COLORS: Record<string, string> = {
  applied: "#3b82f6",
  interviewing: "#a855f7",
  rejected: "#ef4444",
  offered: "#22c55e",
};

function scoreColor(score: number): string {
  if (score >= 80) return "#22c55e";
  if (score >= 60) return "#84cc16";
  if (score >= 40) return "#eab308";
  return "#ef4444";
}

export default function ScoreDistribution({
  scores,
  statuses,
}: ScoreDistributionProps) {
  if (!scores || scores.length === 0) return null;

  const avg = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
  const hasStatuses = statuses && statuses.length === scores.length;

  // For < 5 scores, show individual score cards
  if (scores.length < 5) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span>Average:</span>
          <span className="font-semibold text-foreground">{avg}/100</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {scores.map((score, i) => (
            <div
              key={i}
              className="flex flex-col items-center gap-1 bg-card border rounded-lg px-4 py-3 min-w-[70px]"
            >
              <span
                className="text-lg font-bold"
                style={{ color: scoreColor(score) }}
              >
                {score}
              </span>
              {hasStatuses && (
                <span className="text-[10px] text-muted-foreground capitalize">
                  {statuses[i]}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Dot strip visualization
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {scores.length} applications
        </span>
        <span className="text-muted-foreground">
          Average: <span className="font-semibold text-foreground">{avg}/100</span>
        </span>
      </div>

      {/* Strip */}
      <div className="relative h-12 bg-muted/30 rounded-lg border">
        {/* Gradient background */}
        <div
          className="absolute inset-0 rounded-lg opacity-10"
          style={{
            background:
              "linear-gradient(to right, #ef4444, #eab308, #84cc16, #22c55e)",
          }}
        />

        {/* Score dots */}
        {scores.map((score, i) => {
          const color = hasStatuses
            ? STATUS_COLORS[statuses[i]] || scoreColor(score)
            : scoreColor(score);
          // Jitter y position to avoid perfect overlap
          const yOffset = 12 + ((i * 7) % 24);
          return (
            <div
              key={i}
              className="absolute w-2.5 h-2.5 rounded-full border border-background/50 transition-all hover:scale-150 hover:z-10"
              style={{
                left: `${Math.max(2, Math.min(98, score))}%`,
                top: `${yOffset}px`,
                backgroundColor: color,
                transform: "translateX(-50%)",
              }}
              title={`Score: ${score}${hasStatuses ? ` (${statuses[i]})` : ""}`}
            />
          );
        })}

        {/* Average marker */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-foreground/60"
          style={{ left: `${avg}%` }}
        >
          <div className="absolute -top-5 left-1/2 -translate-x-1/2 text-[10px] font-medium text-foreground whitespace-nowrap">
            avg {avg}
          </div>
        </div>

        {/* Scale labels */}
        <div className="absolute -bottom-5 left-0 text-[10px] text-muted-foreground">
          0
        </div>
        <div className="absolute -bottom-5 left-1/4 text-[10px] text-muted-foreground">
          25
        </div>
        <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[10px] text-muted-foreground">
          50
        </div>
        <div className="absolute -bottom-5 left-3/4 text-[10px] text-muted-foreground">
          75
        </div>
        <div className="absolute -bottom-5 right-0 text-[10px] text-muted-foreground">
          100
        </div>
      </div>

      {/* Legend for statuses */}
      {hasStatuses && (
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground pt-2">
          {Object.entries(STATUS_COLORS).map(([status, color]) => {
            const count = statuses.filter((s) => s === status).length;
            if (count === 0) return null;
            return (
              <div key={status} className="flex items-center gap-1">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="capitalize">
                  {status} ({count})
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
