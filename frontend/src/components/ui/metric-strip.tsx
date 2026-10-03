// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { cn } from "@/lib/utils";

export interface Metric {
  label: string;
  value: React.ReactNode;
  /** Colour the value only when it is above zero and means something needs attention. */
  tone?: "default" | "primary" | "warning" | "danger";
  href?: string;
}

const TONE: Record<NonNullable<Metric["tone"]>, string> = {
  default: "text-foreground",
  primary: "text-primary",
  warning: "text-warning",
  danger: "text-destructive",
};

/** A row of label and value pairs split by hairlines. Replaces pastel stat tiles. */
export function MetricStrip({ metrics, className }: { metrics: Metric[]; className?: string }) {
  return (
    <dl
      className={cn(
        "grid grid-cols-2 divide-border rounded-xl border border-border bg-card sm:flex sm:divide-x",
        className
      )}
    >
      {metrics.map((m) => {
        const body = (
          <>
            <dt className="text-xs font-medium text-muted-foreground">{m.label}</dt>
            <dd className={cn("mt-0.5 font-mono text-lg font-medium", TONE[m.tone ?? "default"])}>
              {m.value}
            </dd>
          </>
        );
        return (
          <div key={m.label} className="min-w-0 flex-1 px-4 py-3">
            {m.href ? (
              <a href={m.href} className="block rounded-md hover:text-primary">
                {body}
              </a>
            ) : (
              body
            )}
          </div>
        );
      })}
    </dl>
  );
}
