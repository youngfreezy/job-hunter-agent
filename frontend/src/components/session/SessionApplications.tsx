// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import Link from "next/link";

import type { LoadedSessionRun } from "./use-session-run";

export function SessionApplications({ run }: { run: Pick<LoadedSessionRun, "session" | "sessionId"> }) {
  const { session, sessionId } = run;
  return (
    <>
      {session.applications_submitted && session.applications_submitted.length > 0 && (
        <section aria-labelledby="sent-h" className="rounded-xl border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <h2 id="sent-h" className="text-base font-semibold">
              Sent
            </h2>
            <Link href={`/session/${sessionId}/manual-apply`} className="text-[13px] font-medium text-primary hover:underline">
              All applications
            </Link>
          </div>
          <ul className="divide-y divide-border text-[13px]">
            {session.applications_submitted.map((app, i) => (
              <li key={i} className="flex items-center gap-2 px-4 py-2.5">
                <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full bg-primary" />
                <span className="min-w-0 flex-1 truncate">
                  {app.job?.title && app.job?.company ? `${app.job.title} at ${app.job.company}` : "Application"}
                </span>
                <span className="text-muted-foreground">{app.status === "submitted" ? "Submitted" : app.status}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

    </>
  );
}
