// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { ChatPanel } from "@/components/ChatPanel";
import { CoachPanel } from "@/components/CoachPanel";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import type { LoadedSessionRun } from "./use-session-run";

export function CoachReviewDialog({ run }: { run: Pick<LoadedSessionRun, "coachReviewOpen" | "setCoachReviewOpen" | "session" | "coachReviewData" | "chatMessages" | "handleSendChat" | "chatLoading" | "coachReviewSubmitting" | "handleApproveCoachReview"> }) {
  const { coachReviewOpen, setCoachReviewOpen, session, coachReviewData, chatMessages, handleSendChat, chatLoading, coachReviewSubmitting, handleApproveCoachReview } = run;
  return (
    <>
      {/* Resume approval (gate 1) */}
      <Dialog open={coachReviewOpen} onOpenChange={setCoachReviewOpen}>
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {session.status === "awaiting_coach_review" ? "Approve your coached resume" : "Resume report"}
            </DialogTitle>
            <DialogDescription>
              {session.status === "awaiting_coach_review"
                ? "The coach rewrote your resume. Approve it to start the search, or keep your original."
                : "What the coach changed and why. This run used the approved version."}
            </DialogDescription>
          </DialogHeader>
          {coachReviewData && (
            <div className="space-y-4">
              <CoachPanel coach={coachReviewData} />
              {session.status === "awaiting_coach_review" && (
                <section className="overflow-hidden rounded-xl border border-border">
                  <h3 className="border-b border-border px-4 py-2.5 text-sm font-semibold">Ask the coach</h3>
                  <div className="h-56">
                    <ChatPanel
                      messages={chatMessages}
                      onSend={handleSendChat}
                      disabled={false}
                      isLoading={chatLoading}
                      placeholder="Ask the coach to change your resume"
                    />
                  </div>
                </section>
              )}
            </div>
          )}
          <DialogFooter className="gap-2 sm:gap-0">
            {session.status === "awaiting_coach_review" ? (
              <>
                <Button variant="ghost" onClick={() => setCoachReviewOpen(false)} disabled={coachReviewSubmitting}>
                  Not now
                </Button>
                <Button variant="outline" onClick={() => handleApproveCoachReview(true)} disabled={coachReviewSubmitting}>
                  Keep my original
                </Button>
                <Button onClick={() => handleApproveCoachReview()} loading={coachReviewSubmitting}>
                  Approve and search
                </Button>
              </>
            ) : (
              <Button variant="outline" onClick={() => setCoachReviewOpen(false)}>
                Close
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </>
  );
}
