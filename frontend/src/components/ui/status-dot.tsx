// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { cn } from "@/lib/utils";
import type { OutcomeTone } from "@/lib/run";

const DOT: Record<OutcomeTone, string> = {
  running: "bg-foreground",
  needs: "bg-warning-border ring-1 ring-warning",
  sent: "bg-primary",
  neutral: "bg-muted-foreground/60",
  failed: "bg-destructive",
};

/** A static 8px dot plus a word. Never pulses. */
export function StatusDot({
  tone,
  children,
  className,
}: {
  tone: OutcomeTone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-[13px]",
        tone === "needs" ? "text-warning" : tone === "failed" ? "text-destructive" : "text-muted-foreground",
        className
      )}
    >
      <span aria-hidden="true" className={cn("h-2 w-2 shrink-0 rounded-full", DOT[tone])} />
      {children}
    </span>
  );
}
