// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { Button } from "@/components/ui/button";

import { checkpointLabel } from "./event-log";
import type { SessionPresentation } from "./presentation";
import type { LoadedSessionRun } from "./use-session-run";

export function SessionCheckpoints({ run, view }: { run: Pick<LoadedSessionRun, "checkpoints" | "rewindLoading" | "handleLoadCheckpoints" | "handleRewind">; view: Pick<SessionPresentation, "finished"> }) {
  const { checkpoints, rewindLoading, handleLoadCheckpoints, handleRewind } = run;
  const { finished } = view;
  return (
    <>
      {finished && (
        <section aria-labelledby="cp-h" className="rounded-xl border border-border bg-card p-4">
          <h2 id="cp-h" className="text-base font-semibold">
            Checkpoints
          </h2>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Pick up from an approval step instead of starting over.
          </p>
          {checkpoints.length === 0 ? (
            <Button size="sm" variant="outline" className="mt-3" onClick={handleLoadCheckpoints}>
              Show checkpoints
            </Button>
          ) : (
            <ul className="mt-3 space-y-2">
              {checkpoints
                .filter((cp) => ["paused", "awaiting_review", "awaiting_coach_review"].includes(cp.status))
                .map((cp) => (
                  <li key={cp.checkpoint_id} className="flex items-center justify-between gap-2 text-[13px]">
                    <span>
                      {checkpointLabel(cp.status)}
                      <span className="ml-1.5 font-mono text-muted-foreground">{cp.application_queue} queued</span>
                    </span>
                    <Button size="sm" variant="outline" disabled={rewindLoading} onClick={() => handleRewind(cp.checkpoint_id)}>
                      Rewind
                    </Button>
                  </li>
                ))}
              {checkpoints.filter((cp) => ["paused", "awaiting_review", "awaiting_coach_review"].includes(cp.status)).length === 0 && (
                <li className="text-[13px] text-muted-foreground">No approval steps to rewind to.</li>
              )}
            </ul>
          )}
        </section>
      )}

    </>
  );
}
