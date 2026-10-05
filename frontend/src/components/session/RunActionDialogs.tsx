// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { AdjustDialog } from "@/components/run/AdjustDialog";
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

export function RunActionDialogs({ run }: { run: Pick<LoadedSessionRun, "stopOpen" | "setStopOpen" | "runAction" | "handleStop" | "rerunOpen" | "setRerunOpen" | "handleRerun" | "adjustOpen" | "session" | "setAdjustOpen"> }) {
  const { stopOpen, setStopOpen, runAction, handleStop, rerunOpen, setRerunOpen, handleRerun, adjustOpen, session, setAdjustOpen } = run;
  return (
    <>
      <Dialog open={stopOpen} onOpenChange={setStopOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Stop this run?</DialogTitle>
            <DialogDescription>
              The agent stops after its current step. Applications already sent stay sent, and you aren&apos;t
              charged for jobs it didn&apos;t reach.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setStopOpen(false)}>
              Keep running
            </Button>
            <Button variant="destructive" loading={runAction === "stop"} onClick={() => void handleStop()}>
              Stop run
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={rerunOpen} onOpenChange={setRerunOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Run this search again</DialogTitle>
            <DialogDescription>
              Same roles and location. You approve the shortlist before anything is sent. Each application sent
              costs 1 credit.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRerunOpen(false)}>
              Cancel
            </Button>
            <Button loading={runAction === "rerun"} onClick={() => void handleRerun()}>
              Start run
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {adjustOpen && (
        <AdjustDialog
          run={session}
          busy={runAction === "rerun"}
          costLine="You approve the shortlist before anything is sent. Each application sent costs 1 credit."
          onCancel={() => setAdjustOpen(false)}
          onStart={(o) => void handleRerun(o)}
        />
      )}

    </>
  );
}
