// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { LiveViewState } from "@/lib/liveView";
import { BrowserbaseExplainer } from "@/components/BrowserbaseExplainer";

interface LiveBrowserPanelProps {
  liveView: LiveViewState;
  jobLabel?: string;
  onHide?: () => void;
}

/**
 * Embeds a cloud browser's Live View (Browserbase) for the job being applied
 * to. Replaces the screenshot feed: the iframe is the real browser, so the
 * user can watch and, if the agent pauses, take over directly in it.
 */
export function LiveBrowserPanel({ liveView, jobLabel, onHide }: LiveBrowserPanelProps) {
  return (
    <Card className="mb-4 overflow-hidden">
      <CardHeader className="border-b border-border/50 pb-2">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-sm font-semibold flex items-center gap-2 min-w-0">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="truncate">Live browser{jobLabel ? ` — ${jobLabel}` : ""}</span>
            <Badge variant="secondary" className="text-[11px] shrink-0">
              {liveView.provider}
            </Badge>
          </CardTitle>
          <div className="flex items-center gap-2 shrink-0">
            <a
              href={liveView.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-600 hover:underline dark:text-blue-400"
            >
              Open in new tab
            </a>
            {onHide && (
              <Button variant="ghost" size="sm" onClick={onHide} aria-label="Hide live browser">
                Hide
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      {process.env.NEXT_PUBLIC_BROWSERBASE_DEMO === "true" && (
        <div className="border-b border-border/50 px-3 py-1"><BrowserbaseExplainer compact /></div>
      )}
      <CardContent className="p-0 bg-zinc-900">
        <iframe
          key={liveView.url}
          src={liveView.url}
          title={`Live browser view${jobLabel ? ` for ${jobLabel}` : ""}`}
          className="block w-full aspect-video min-h-[360px] border-0"
          allow="clipboard-read; clipboard-write"
          referrerPolicy="no-referrer"
        />
        {liveView.browserbaseSessionId && (
          <p className="px-3 py-1.5 text-[11px] font-mono text-zinc-400">
            session {liveView.browserbaseSessionId}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
