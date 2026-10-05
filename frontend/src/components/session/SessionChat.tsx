// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { ChatPanel } from "@/components/ChatPanel";

import type { SessionPresentation } from "./presentation";
import type { LoadedSessionRun } from "./use-session-run";

export function SessionChat({ run, view }: { run: Pick<LoadedSessionRun, "quickActions" | "sendSuggestedMessage" | "chatMessages" | "handleSendChat" | "chatLoading" | "coachChatMode">; view: Pick<SessionPresentation, "finished"> }) {
  const { quickActions, sendSuggestedMessage, chatMessages, handleSendChat, chatLoading, coachChatMode } = run;
  const { finished } = view;
  return (
    <>
      <section aria-labelledby="chat-h" className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="px-4 pt-4">
          <h2 id="chat-h" className="text-base font-semibold">
            {finished ? "Ask about this run" : "Guide the agent"}
          </h2>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {quickActions.map((action) => (
              <button
                key={action}
                type="button"
                onClick={() => sendSuggestedMessage(action)}
                className="rounded-full border border-border bg-card px-3 py-1 text-left text-[13px] text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5"
              >
                {action}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-3 h-64">
          <ChatPanel
            emptyText={
              finished
                ? "Answers come from this run's log and results."
                : "The agent reads your message before its next step."
            }
            messages={chatMessages}
            onSend={handleSendChat}
            disabled={false}
            isLoading={chatLoading}
            placeholder={
              coachChatMode
                ? "Ask the coach to change your resume"
                : finished
                  ? "Ask why a job was removed"
                  : "Tell the agent what to change"
            }
          />
        </div>
      </section>

    </>
  );
}
