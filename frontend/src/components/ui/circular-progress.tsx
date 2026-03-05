import * as React from "react";
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
}

const CircularProgress = React.forwardRef<HTMLDivElement, CircularProgressProps>(
  ({ value, size = 40, strokeWidth = 4, showValue = false, className, ...props }, ref) => {
    const clamped = Math.max(0, Math.min(100, value));
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (clamped / 100) * circumference;

    return (
      <div
        ref={ref}
        className={cn("relative inline-flex items-center justify-center", className)}
        style={{ width: size, height: size }}
        {...props}
      >
        <svg width={size} height={size} className="-rotate-90">
          {/* Background ring */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            className="text-zinc-200 dark:text-zinc-800"
          />
          {/* Foreground ring */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="text-blue-600 dark:text-blue-400 transition-[stroke-dashoffset] duration-300 ease-in-out"
          />
        </svg>
        {showValue && (
          <span className="absolute text-[10px] font-medium text-zinc-700 dark:text-zinc-300">
            {Math.round(clamped)}
          </span>
        )}
      </div>
    );
  }
);
CircularProgress.displayName = "CircularProgress";

export { CircularProgress };
