// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { Fragment } from "react";

import {
  PHASES
} from "@/lib/run";
import { cn } from "@/lib/utils";

import type { SessionPresentation } from "./presentation";

export function SessionActivity({ view }: { view: Pick<SessionPresentation, "logRows" | "finished"> }) {
  const { logRows, finished } = view;
  return (
    <>
      <section aria-labelledby="log-h" className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 id="log-h" className="text-base font-semibold">
            Activity
          </h2>
          <span className="font-mono text-xs text-muted-foreground">
            {logRows.length} {logRows.length === 1 ? "event" : "events"}
          </span>
        </div>
        {logRows.length === 0 ? (
          <p className="px-4 py-8 text-sm text-muted-foreground">
            {finished ? "This run has no saved activity." : "Waiting for the first update from the agent."}
          </p>
        ) : (
          <div role="log" aria-live="polite" aria-label="Run activity">
            <table className="w-full border-collapse text-[13px]">
              <tbody>
                {logRows.map((r, i) => {
                  const head = i === 0 || logRows[i - 1].group !== r.group;
                  return (
                    <Fragment key={i}>
                      {head && (
                        <tr className="border-t border-border bg-surface-2 first:border-t-0">
                          <th colSpan={3} scope="colgroup" className="px-4 py-2 text-left font-medium text-muted-foreground">
                            {PHASES.find((p) => p.key === r.group)?.label}
                          </th>
                        </tr>
                      )}
                      <tr className="border-t border-border align-top max-sm:flex max-sm:flex-wrap max-sm:px-4 max-sm:py-2.5">
                        <td className="w-16 whitespace-nowrap py-2.5 pl-4 pr-2 font-mono text-muted-foreground max-sm:w-auto max-sm:p-0 max-sm:pr-2">
                          {r.t}
                        </td>
                        <td className="w-24 py-2.5 pr-2 text-muted-foreground max-sm:w-auto max-sm:p-0">{r.step}</td>
                        <td
                          className={cn(
                            "py-2.5 pr-4 max-sm:basis-full max-sm:p-0 max-sm:pt-0.5",
                            r.tone === "error" ? "text-destructive" : r.tone === "needs" ? "text-warning" : "text-foreground"
                          )}
                        >
                          {r.text}
                        </td>
                      </tr>
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

    </>
  );
}
