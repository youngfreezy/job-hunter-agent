// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

import type { LoadedSessionRun } from "./use-session-run";

export function ShortlistReviewDialog({ run }: { run: Pick<LoadedSessionRun, "shortlistReviewOpen" | "setShortlistReviewOpen" | "shortlistJobs" | "selectedJobIds" | "selectedCompanyCounts" | "toggleJobSelection" | "shortlistSubmitting" | "handleApproveShortlist"> }) {
  const { shortlistReviewOpen, setShortlistReviewOpen, shortlistJobs, selectedJobIds, selectedCompanyCounts, toggleJobSelection, shortlistSubmitting, handleApproveShortlist } = run;
  return (
    <>
      {/* Shortlist approval (gate 2) */}
      <Dialog open={shortlistReviewOpen} onOpenChange={setShortlistReviewOpen}>
        <DialogContent className="flex max-h-[85vh] max-w-3xl flex-col">
          <DialogHeader>
            <DialogTitle>Approve the shortlist</DialogTitle>
            <DialogDescription>
              Only jobs that meet your search criteria are preselected. Review each unresolved job before selecting it; jobs that violate your search criteria cannot be selected. Only approved jobs are sent, at 1 credit each.
            </DialogDescription>
          </DialogHeader>
          <div role="group" aria-label="Jobs on the shortlist" className="-mx-1 min-h-0 flex-1 space-y-2 overflow-y-auto px-1 py-1">
            {shortlistJobs.map((sj) => {
              const selected = selectedJobIds.has(sj.job.id);
              const companyKey = sj.job.company.toLowerCase().trim();
              const isDuplicateCompany = selected && (selectedCompanyCounts.get(companyKey) || 0) > 1;
              return (
                <label
                  key={sj.job.id}
                  className={cn(
                    "flex cursor-pointer gap-3 rounded-xl border p-4 transition-colors",
                    selected ? "border-primary/40 bg-primary/5" : "border-border hover:bg-surface-2"
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selected}
                    disabled={sj.eligibility_status === "not_met"}
                    onChange={() => toggleJobSelection(sj.job.id)}
                    className="mt-0.5 h-4 w-4 shrink-0 accent-[hsl(var(--primary))]"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-baseline justify-between gap-x-3">
                      <span className="text-sm font-medium">{sj.job.title}</span>
                      <span className="font-mono text-sm">
                        {sj.score}
                        <span className="text-muted-foreground"> / 100</span>
                      </span>
                    </span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                      {sj.job.company} · {sj.job.location}
                      <Badge variant="secondary" className="font-normal capitalize">
                        {sj.job.board}
                      </Badge>
                      {isDuplicateCompany && (
                        <Badge variant="warning" className="font-normal">
                          Only 1 per company is sent
                        </Badge>
                      )}
                    </span>
                    <span className="mt-2 block">
                      <Badge variant={sj.eligibility_status === "met" ? "secondary" : "warning"}>
                        {sj.eligibility_status === "met" ? "Search criteria met" : sj.eligibility_status === "not_met" ? "Search criteria not met" : "Search criteria need review"}
                      </Badge>
                      {(sj.eligibility_reasons?.length ? sj.eligibility_reasons : sj.eligibility_status !== "met" ? ["Your search criteria have not been fully assessed. Check the listing before selecting this job."] : []).map((reason, index) => (
                        <span key={index} className="mt-1 block text-xs leading-relaxed text-muted-foreground">{reason}</span>
                      ))}
                    </span>
                    {sj.fit_summary && (
                      <span className="mt-2 block text-xs leading-relaxed text-muted-foreground">{sj.fit_summary}</span>
                    )}
                  </span>
                </label>
              );
            })}
          </div>
          <DialogFooter className="flex-col items-stretch gap-2 sm:flex-row sm:items-center sm:justify-between">
            <span className="font-mono text-sm text-muted-foreground">
              {selectedJobIds.size} of {shortlistJobs.length} selected
            </span>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setShortlistReviewOpen(false)} disabled={shortlistSubmitting}>
                Not now
              </Button>
              <Button onClick={handleApproveShortlist} loading={shortlistSubmitting} disabled={selectedJobIds.size === 0}>
                Approve {selectedJobIds.size} {selectedJobIds.size === 1 ? "job" : "jobs"}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </>
  );
}
