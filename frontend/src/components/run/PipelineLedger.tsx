// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { cn } from "@/lib/utils";
import type { GateState, LedgerPhase, PhaseState } from "@/lib/run";

const BAR: Record<PhaseState, string> = {
  done: "bg-primary",
  current: "bg-primary/25 ledger-current",
  todo: "bg-muted",
  empty: "border border-dashed border-muted-foreground/40 bg-transparent",
};

const STATE_WORD: Record<PhaseState, string> = {
  done: "done",
  current: "in progress",
  todo: "not started",
  empty: "nothing passed",
};

const GATE_WORD: Record<GateState, string> = {
  passed: "approved",
  open: "waiting for you",
  todo: "not reached",
};

function Gate({ state, label, compact }: { state: GateState; label: string; compact?: boolean }) {
  return (
    <li
      className={cn("flex shrink-0 justify-center", compact ? "w-3 items-center" : "w-3 pt-[42px] sm:w-5 sm:pt-[46px]")}
      aria-label={`${label} approval: ${GATE_WORD[state]}`}
      title={`${label} approval: ${GATE_WORD[state]}`}
    >
      <span
        aria-hidden="true"
        className={cn(
          "block rotate-45 rounded-[2px] border-[1.5px]",
          compact ? "h-[7px] w-[7px]" : "h-2.5 w-2.5",
          state === "passed" && "border-primary bg-primary",
          state === "open" && "border-warning bg-warning-border",
          state === "todo" && "border-muted-foreground/50 bg-card"
        )}
      />
    </li>
  );
}

/**
 * The run's signature: five phases with live counts and the two approval gates
 * drawn as notches (after Resume and after Shortlist).
 */
export function PipelineLedger({
  phases,
  gates,
  compact,
  caption,
  className,
}: {
  phases: LedgerPhase[];
  gates: { coach: GateState; shortlist: GateState };
  compact?: boolean;
  /** Compact only: a short mono line under the bars, such as "43 found · 0 sent". */
  caption?: string;
  className?: string;
}) {
  const items: React.ReactNode[] = [];
  phases.forEach((p, i) => {
    items.push(
      compact ? (
        <li key={p.key} className="min-w-0 flex-1" title={`${p.label}: ${STATE_WORD[p.state]}`}>
          <span className={cn("block h-1.5 rounded-full", BAR[p.state])} />
          <span className="sr-only">
            {p.label}
            {p.count != null ? `, ${p.count} ${p.unit}` : ""}, {STATE_WORD[p.state]}
          </span>
        </li>
      ) : (
        <li key={p.key} className="flex min-w-0 flex-1 flex-col gap-1.5 sm:min-w-[96px]">
          <span className="truncate text-xs font-medium text-muted-foreground sm:text-[13px]">{p.label}</span>
          <span className="flex items-baseline gap-1.5">
            <span
              className={cn(
                "font-mono text-xl font-medium leading-none",
                p.state === "empty" ? "text-muted-foreground" : "text-foreground"
              )}
            >
              {p.count ?? "–"}
            </span>
            {p.count != null && p.unit && (
              <span className="hidden text-xs text-muted-foreground sm:inline">{p.unit}</span>
            )}
          </span>
          <span className={cn("block h-1.5 rounded-full transition-colors duration-200", BAR[p.state])} />
          <span className="hidden min-h-[1rem] text-xs leading-snug text-muted-foreground sm:block">
            {p.reason}
            <span className="sr-only">{STATE_WORD[p.state]}</span>
          </span>
        </li>
      )
    );
    if (i === 0) items.push(<Gate key="g1" state={gates.coach} label="Resume" compact={compact} />);
    if (i === 2) items.push(<Gate key="g2" state={gates.shortlist} label="Shortlist" compact={compact} />);
  });

  if (compact) {
    return (
      <div className={cn("flex w-full min-w-[160px] max-w-[240px] flex-col gap-1", className)}>
        <ol className="relative flex items-center gap-[3px]" aria-label="Pipeline">
          {items}
        </ol>
        {caption && <span className="font-mono text-xs text-muted-foreground">{caption}</span>}
      </div>
    );
  }

  const reason = phases.find((p) => p.reason)?.reason;
  return (
    <div className={cn("relative", className)}>
      <ol className="relative flex items-start gap-1.5 sm:gap-2" aria-label="Pipeline">
        {items}
      </ol>
      {reason && <p className="mt-2 text-xs text-muted-foreground sm:hidden">{reason}</p>}
    </div>
  );
}
