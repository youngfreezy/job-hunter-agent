// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { Button } from "@/components/ui/button";

import type { LoadedSessionRun } from "./use-session-run";

export function SessionNeedsQueue({ run }: { run: Pick<LoadedSessionRun, "submitConfirmData" | "interventionData" | "loginPrompt" | "handleSubmitDecision"> }) {
  const { submitConfirmData, interventionData, loginPrompt, handleSubmitDecision } = run;
  return (
    <>
      {(submitConfirmData || interventionData || loginPrompt) && (
        <section aria-labelledby="queue-h" className="rounded-xl border border-warning-border bg-card p-4">
          <h2 id="queue-h" className="text-base font-semibold">
            Needs you
          </h2>
          <ul className="mt-2 space-y-3 text-sm">
            {submitConfirmData && (
              <li>
                <p>
                  Submit {submitConfirmData.job_title} at {submitConfirmData.company}?
                </p>
                <div className="mt-2 flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => void handleSubmitDecision("skip")}>
                    Skip
                  </Button>
                  <Button size="sm" onClick={() => void handleSubmitDecision("submit")}>
                    Submit
                  </Button>
                </div>
              </li>
            )}
            {interventionData && (
              <li className="text-warning">
                {interventionData.job_title}: {interventionData.reason}
              </li>
            )}
            {loginPrompt && <li>Sign in to {loginPrompt.board} in the browser window.</li>}
          </ul>
        </section>
      )}

    </>
  );
}
