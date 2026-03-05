"use client";

import * as React from "react";
import { CircularProgressbar, buildStyles } from "react-circular-progressbar";
import "react-circular-progressbar/dist/styles.css";
import { cn } from "@/lib/utils";

interface CircularProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  /** 0–100 percentage filled */
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

const CircularProgress = React.forwardRef<HTMLDivElement, CircularProgressProps>(
  ({ value, size = 40, strokeWidth = 4, showValue = false, pulse = false, className, ...props }, ref) => {
    const clamped = Math.max(0, Math.min(100, value));
    // Convert strokeWidth from px to percentage of viewbox (which is 100x100)
    const strokeWidthPct = (strokeWidth / size) * 100;

    return (
      <div
        ref={ref}
        className={cn(
          "relative inline-flex items-center justify-center",
          pulse && "animate-[spin-pulse_2s_ease-in-out_infinite]",
          className,
        )}
        style={{ width: size, height: size }}
        {...props}
      >
        <CircularProgressbar
          value={clamped}
          text={showValue ? `${Math.round(clamped)}` : undefined}
          strokeWidth={strokeWidthPct}
          styles={buildStyles({
            textSize: "26px",
            textColor: "var(--cp-text)",
            pathColor: "var(--cp-path)",
            trailColor: "var(--cp-trail)",
            pathTransitionDuration: 0.3,
            strokeLinecap: "round",
          })}
        />
      </div>
    );
  }
);
CircularProgress.displayName = "CircularProgress";

export { CircularProgress };
