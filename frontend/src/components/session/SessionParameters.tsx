// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import type { CoachOutput } from "@/lib/api";

import type { SessionPresentation } from "./presentation";
import { QuickApplyUrls } from "./QuickApplyUrls";
import type { LoadedSessionRun } from "./use-session-run";

export function SessionParameters({ run, view }: { run: Pick<LoadedSessionRun, "session" | "setAdjustOpen" | "setCoachReviewData" | "setCoachReviewOpen">; view: Pick<SessionPresentation, "finished" | "threshold" | "uncertainCount" | "submittedCount" | "failedCount"> }) {
  const { session, setAdjustOpen, setCoachReviewData, setCoachReviewOpen } = run;
  const { finished, threshold, uncertainCount, submittedCount, failedCount } = view;
  return (
    <>
      <section aria-labelledby="params-h" className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-baseline justify-between">
          <h2 id="params-h" className="text-base font-semibold">
            Parameters
          </h2>
          {finished && (
            <button type="button" onClick={() => setAdjustOpen(true)} className="text-[13px] font-medium text-primary hover:underline">
              Adjust
            </button>
          )}
        </div>
        <dl className="mt-3 grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-2.5 text-[13px]">
          <dt className="text-muted-foreground">Roles</dt>
          <dd className="flex flex-wrap gap-1">
            {(session.keywords ?? []).map((kw) => (
              <Badge key={kw} variant="secondary" className="font-normal">
                {kw}
              </Badge>
            ))}
          </dd>
          <dt className="text-muted-foreground">Location</dt>
          <dd>{session.remote_only ? "Remote only" : session.locations?.join(", ") || "Anywhere"}</dd>
          {session.salary_min != null && session.salary_min > 0 && (
            <>
              <dt className="text-muted-foreground">Salary floor</dt>
              <dd className="font-mono">${session.salary_min.toLocaleString()}</dd>
            </>
          )}
          {threshold != null && (
            <>
              <dt className="text-muted-foreground">Score cutoff</dt>
              <dd className="font-mono">{threshold}</dd>
            </>
          )}
          <dt className="text-muted-foreground">Approval</dt>
          <dd>
            {session.session_config?.discovery_mode === "manual_urls"
              ? "You approved these job links in Quick Apply"
              : "You approve the shortlist before anything is sent"}
          </dd>
          <dt className="text-muted-foreground">Credit estimate</dt>
          <dd>
            <span className="font-mono">{uncertainCount > 0 ? "Pending confirmation" : submittedCount + failedCount * 0.5}</span>
            <span className="mt-0.5 block text-xs text-muted-foreground">
              Before free applications or plan coverage. <Link href="/billing" className="underline">View actual charges</Link>.
            </span>
          </dd>
          {session.coach_output?.resume_score && (
            <>
              <dt className="text-muted-foreground">Resume</dt>
              <dd>
                <span className="font-mono">{session.coach_output.resume_score.overall} / 100</span>
                {session.coach_output.confidence_message && (
                  <span className="mt-0.5 block text-muted-foreground">
                    {session.coach_output.confidence_message}
                  </span>
                )}
                {session.coach_output && (
                  <button
                    type="button"
                    onClick={() => {
                      setCoachReviewData(session.coach_output as CoachOutput);
                      setCoachReviewOpen(true);
                    }}
                    className="mt-0.5 font-medium text-primary hover:underline"
                  >
                    Full report
                  </button>
                )}
              </dd>
            </>
          )}
        </dl>
        {session.session_config?.discovery_mode === "manual_urls" &&
          (session.session_config?.job_urls?.length || session.job_urls?.length) && (
            <QuickApplyUrls
              urls={session.session_config?.job_urls || session.job_urls || []}
              submitted={submittedCount}
              failed={failedCount + uncertainCount}
            />
          )}
      </section>

    </>
  );
}
