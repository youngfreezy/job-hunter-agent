// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import * as React from "react";
import { cn } from "@/lib/utils";

interface CircularProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  /** 0-100 percentage filled */
  value: number;
  /** Diameter in pixels (default 40) */
  size?: number;
  /** Ring thickness in pixels (default 4) */
  strokeWidth?: number;
  /** Show percentage text in center */
  showValue?: boolean;
  /** Pulse animation when actively progressing (default false) */
  pulse?: boolean;
}

const CircularProgress = React.forwardRef<
  HTMLDivElement,
  CircularProgressProps
>(
  (
    {
      value,
      size = 40,
      strokeWidth = 4,
      showValue = false,
      pulse = false,
      className,
      ...props
    },
    ref
  ) => {
    const clamped = Math.max(0, Math.min(100, value));
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (clamped / 100) * circumference;
    const gradientId = React.useId();

    const scoreColor = () => {
      if (clamped >= 80) return { from: "#22c55e", to: "#16a34a" };
      if (clamped >= 60) return { from: "#6366f1", to: "#8b5cf6" };
      if (clamped >= 40) return { from: "#f59e0b", to: "#eab308" };
      return { from: "#ef4444", to: "#dc2626" };
    };
    const colors = scoreColor();

    return (
      <div
        ref={ref}
        className={cn(
          "relative inline-flex items-center justify-center",
          pulse && "animate-[spin-pulse_2s_ease-in-out_infinite]",
          className
        )}
        style={{ width: size, height: size }}
        {...props}
      >
        <svg width={size} height={size} className="-rotate-90">
          <defs>
            <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={colors.from} />
              <stop offset="100%" stopColor={colors.to} />
            </linearGradient>
          </defs>
          {/* Background ring */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            strokeWidth={strokeWidth}
            className="stroke-blue-100 dark:stroke-blue-950/50"
          />
          {/* Foreground ring */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={`url(#${gradientId})`}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="transition-[stroke-dashoffset] duration-500 ease-out"
            style={{
              filter:
                clamped > 0
                  ? `drop-shadow(0 0 3px ${colors.from}40)`
                  : undefined,
            }}
          />
        </svg>
        {showValue && (
          <span className="absolute text-[10px] font-bold text-foreground/80">
            {Math.round(clamped)}
          </span>
        )}
      </div>
    );
  }
);
CircularProgress.displayName = "CircularProgress";

export { CircularProgress };
