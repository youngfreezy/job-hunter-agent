// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useState } from "react";
import { toast } from "sonner";

import { PipelineLedger } from "@/components/run/PipelineLedger";
import { Button } from "@/components/ui/button";
import { StatusDot } from "@/components/ui/status-dot";

import type { SessionPresentation } from "./presentation";
import type { LoadedSessionRun } from "./use-session-run";

export function SessionStatus({ run, view }: { run: Pick<LoadedSessionRun, "session" | "shortlistJobs" | "interventionData" | "submitConfirmData" | "liveView" | "sseConnected" | "sseFailCount" | "setCoachReviewOpen" | "setShortlistReviewOpen" | "handleResumeIntervention" | "handleResumeRun" | "setAdjustOpen" | "setRerunOpen" | "handleSubmitDecision" | "runAction" | "handlePause" | "setStopOpen">; view: Pick<SessionPresentation, "status" | "finished" | "running" | "submittedCount" | "uncertainCount" | "ledger" | "stateTone" | "stateLine"> }) {
  const { session, shortlistJobs, interventionData, submitConfirmData, liveView, sseConnected, sseFailCount, setCoachReviewOpen, setShortlistReviewOpen, handleResumeIntervention, handleResumeRun, setAdjustOpen, setRerunOpen, handleSubmitDecision, runAction, handlePause, setStopOpen } = run;
  const { status, finished, running, submittedCount, uncertainCount, ledger, stateTone, stateLine } = view;
  // The one thing the user can do next. A run that sent nothing never offers "success".
  const shortlistCount = shortlistJobs.length || session.scored_jobs?.length || 0;
  const primary: { label: string; onClick: () => void } | null =
    status === "awaiting_coach_review"
      ? { label: "Review resume", onClick: () => setCoachReviewOpen(true) }
      : status === "awaiting_review"
        ? { label: `Review shortlist · ${shortlistCount} jobs`, onClick: () => setShortlistReviewOpen(true) }
        : interventionData
          ? { label: "Resume agent", onClick: () => void handleResumeIntervention() }
          : status === "paused"
            ? { label: "Resume run", onClick: () => void handleResumeRun() }
            : finished && uncertainCount > 0
              ? null
              : finished && submittedCount === 0
                ? { label: "Adjust search", onClick: () => setAdjustOpen(true) }
                : finished
                  ? { label: "Run again", onClick: () => setRerunOpen(true) }
                  : null;

  // Needs-you bar: the open gate or intervention, pinned under the header.
  const needs: { key: string; text: React.ReactNode; actions: React.ReactNode } | null = submitConfirmData
    ? {
      key: `submit-${submitConfirmData.job_id}`,
      text: (
        <>
          <strong className="font-semibold">Ready to submit {submitConfirmData.job_title}</strong> at{" "}
          {submitConfirmData.company}. {submitConfirmData.fields_filled} fields filled. Check the form, then
          submit or skip.
        </>
      ),
      actions: (
        <>
          <Button size="sm" variant="outline" onClick={() => void handleSubmitDecision("skip")}>
            Skip
          </Button>
          <Button size="sm" onClick={() => void handleSubmitDecision("submit")}>
            Submit application
          </Button>
        </>
      ),
    }
    : interventionData
      ? {
        key: `help-${interventionData.job_id}`,
        text: (
          <>
            <strong className="font-semibold">
              {interventionData.job_title} at {interventionData.company} needs your help.
            </strong>{" "}
            {interventionData.reason} Fix it in the browser{liveView ? " below" : ""}, then resume.
          </>
        ),
        actions: (
          <Button size="sm" onClick={() => void handleResumeIntervention()}>
            Resume agent
          </Button>
        ),
      }
      : status === "awaiting_review"
        ? {
          key: "shortlist",
          text: (
            <>
              <strong className="font-semibold">Shortlist waiting for you.</strong> {shortlistCount}{" "}
              {shortlistCount === 1 ? "job" : "jobs"} ready for review. Check search criteria notes before approving.
            </>
          ),
          actions: (
            <Button size="sm" onClick={() => setShortlistReviewOpen(true)}>
              Review {shortlistCount} {shortlistCount === 1 ? "job" : "jobs"}
            </Button>
          ),
        }
        : status === "awaiting_coach_review"
          ? {
            key: "coach",
            text: (
              <>
                <strong className="font-semibold">Your coached resume is ready.</strong> Approve it, or keep your
                original, before the search starts.
              </>
            ),
            actions: (
              <Button size="sm" onClick={() => setCoachReviewOpen(true)}>
                Review resume
              </Button>
            ),
          }
          : null;

  const [needsDismissed, setNeedsDismissed] = useState<string | null>(null);
  const showNeeds = needs && needsDismissed !== needs.key;
  return (
    <>
      <section aria-label="Run status" className="rounded-xl border border-border bg-card px-5 pt-5">
        <PipelineLedger phases={ledger.phases} gates={ledger.gates} />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-border py-3">
          <p className="flex min-w-0 items-center gap-2 text-sm" aria-live="polite">
            <StatusDot tone={stateTone} className="text-foreground">
              <span className="text-foreground">{stateLine}</span>
            </StatusDot>
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {running && (
              <>
                <Button size="sm" variant="outline" loading={runAction === "pause"} onClick={() => void handlePause()}>
                  Pause
                </Button>
                <Button size="sm" variant="outline" className="text-destructive" onClick={() => setStopOpen(true)}>
                  Stop run
                </Button>
              </>
            )}
            {finished && submittedCount === 0 && (
              <Button size="sm" variant="outline" onClick={() => setRerunOpen(true)}>
                Run again
              </Button>
            )}
            {primary && (
              <Button size="sm" onClick={primary.onClick}>
                {primary.label}
              </Button>
            )}
          </div>
        </div>
      </section>

      {showNeeds && needs && (
        <div
          role="status"
          className="sticky top-14 z-30 mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-warning-border bg-warning-surface px-4 py-3 text-sm text-warning lg:top-2"
        >
          <p className="min-w-0 flex-1 basis-72">{needs.text}</p>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="ghost"
              className="text-warning hover:bg-warning-border/30"
              onClick={() => {
                setNeedsDismissed(needs.key);
                toast("It will wait for you on Home.");
              }}
            >
              Not now
            </Button>
            {needs.actions}
          </div>
        </div>
      )}

      {!sseConnected && !finished && (
        <p className="mt-3 rounded-xl border border-border bg-card px-4 py-2.5 text-sm" role="status">
          {sseFailCount >= 5 ? (
            <>
              Lost the live connection. The run continues in the background.{" "}
              <button type="button" className="font-medium text-primary underline" onClick={() => window.location.reload()}>
                Reload
              </button>
            </>
          ) : (
            "Reconnecting to the live log…"
          )}
        </p>
      )}

    </>
  );
}
