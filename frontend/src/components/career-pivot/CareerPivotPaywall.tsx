// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { Button } from "@/components/ui/button";
import type {
  PivotRole
} from "@/lib/types/career-pivot";

type Props = {
  paywall: { count: number; message: string; cost: number } | null;
  pivots: PivotRole[];
  walletBalance: number | null;
  unlocking: boolean;
  handleUnlock: () => void;
  onBuyCredits: () => void;
};

export function CareerPivotPaywall({ paywall, pivots, walletBalance, unlocking, handleUnlock, onBuyCredits }: Props) {
  return <>
    {/* Paywall — unlock pivot roles with blurred chart preview */}
    {paywall && pivots.length === 0 && (
      <div className="space-y-4">
        {/* Blurred chart preview */}
        <div className="bg-card border rounded-lg p-6 relative overflow-hidden">
          <div className="blur-sm select-none pointer-events-none opacity-60">
            <h2 className="text-lg font-medium mb-2">Career Comparison</h2>
            <div className="h-[280px] flex items-end gap-3 px-8">
              {Array.from({ length: paywall.count }, (_, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-2">
                  <div
                    className="w-full rounded-t bg-primary/40"
                    style={{ height: `${120 + i * 40}px` }}
                  />
                  <div className="h-3 w-16 bg-muted rounded" />
                </div>
              ))}
            </div>
            <div className="flex justify-between px-8 mt-2 text-xs text-muted-foreground">
              <span>Higher Skill Match →</span>
              <span>Higher Salary →</span>
            </div>
          </div>
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/60 backdrop-blur-[2px]">
            <div className="text-4xl mb-3">&#128274;</div>
            <h3 className="text-lg font-semibold">{paywall.message}</h3>
            <p className="text-sm text-muted-foreground mt-1 max-w-md text-center">
              See salary data, skill comparisons, learning plans, and personalized charts for each
              role.
            </p>
            <div className="flex items-center gap-3 mt-4">
              <Button onClick={handleUnlock} loading={unlocking} size="lg">
                Unlock for {paywall.cost} Credit
              </Button>
              <Button variant="outline" size="lg" onClick={onBuyCredits}>
                Buy Credits
              </Button>
            </div>
            {walletBalance !== null && (
              <p className="text-xs text-muted-foreground mt-2">
                Current balance: {walletBalance} credit{walletBalance !== 1 ? "s" : ""}
              </p>
            )}
          </div>
        </div>

        {/* Blurred role cards preview */}
        {Array.from({ length: Math.min(paywall.count, 3) }, (_, i) => (
          <div key={i} className="bg-card border rounded-lg p-6 relative overflow-hidden">
            <div className="blur-sm select-none pointer-events-none opacity-50 space-y-3">
              <div className="flex items-center justify-between">
                <div className="h-5 w-48 bg-muted rounded" />
                <div className="h-4 w-24 bg-muted rounded" />
              </div>
              <div className="w-full bg-muted rounded-full h-2">
                <div
                  className="bg-primary/40 h-2 rounded-full"
                  style={{ width: `${50 + i * 15}%` }}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="h-4 w-32 bg-muted rounded" />
                <div className="h-4 w-28 bg-muted rounded" />
                <div className="h-4 w-36 bg-muted rounded" />
                <div className="h-4 w-24 bg-muted rounded" />
              </div>
            </div>
          </div>
        ))}
      </div>
    )}

  </>;
}
