// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

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

export function SessionLoginDialog({ run }: { run: Pick<LoadedSessionRun, "loginPrompt" | "loginConfirming" | "handleConfirmLogin"> }) {
  const { loginPrompt, loginConfirming, handleConfirmLogin } = run;
  return (
    <>
      {/* Pre-login modal */}
      <Dialog open={!!loginPrompt} onOpenChange={() => { }}>
        <DialogContent className="sm:max-w-md" onInteractOutside={(e) => e.preventDefault()}>
          <DialogHeader>
            <DialogTitle>
              Sign in to {loginPrompt?.board?.replace(/^\w/, (c) => c.toUpperCase())}
            </DialogTitle>
            <DialogDescription>{loginPrompt?.message}</DialogDescription>
          </DialogHeader>
          <div className="bg-muted/50 rounded p-3 text-sm text-muted-foreground">
            A browser window is open on the sign-in page. Sign in with your account, then continue.
          </div>
          <DialogFooter>
            <Button
              onClick={handleConfirmLogin}
              loading={loginConfirming}
            >
              I&apos;ve signed in, continue
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </>
  );
}
