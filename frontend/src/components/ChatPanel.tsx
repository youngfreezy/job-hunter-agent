// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type ChatMessage = {
  role: "user" | "agent" | "system";
  text: string;
  timestamp?: string;
};

interface ChatPanelProps {
  messages: ChatMessage[];
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatPanel({ messages, onSend, disabled, placeholder }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages.length]);

  const handleSend = () => {
    if (!input.trim() || disabled) return;
    onSend(input.trim());
    setInput("");
  };

  return (
    <div className="flex flex-col h-full">
      <div ref={containerRef} className="flex-1 overflow-y-auto space-y-2 p-3 min-h-0">
        {messages.length === 0 && (
          <p className="text-zinc-400 text-sm text-center py-4">
            Chat with the agent to steer it in real-time.
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`text-sm rounded-lg px-3 py-2 max-w-[85%] ${
              msg.role === "user"
                ? "bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100 ml-auto"
                : msg.role === "system"
                ? "bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 mx-auto text-center text-xs"
                : "bg-zinc-100 dark:bg-zinc-800"
            }`}
          >
            {msg.role !== "system" && (
              <span className="font-medium text-xs block mb-0.5">
                {msg.role === "user" ? "You" : "Agent"}
              </span>
            )}
            {msg.text}
          </div>
        ))}
        <div />
      </div>
      <div className="border-t border-zinc-200 dark:border-zinc-800 p-3 flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder={placeholder || "Steer the agent... e.g. 'Skip this job'"}
          disabled={disabled}
        />
        <Button size="sm" onClick={handleSend} disabled={disabled || !input.trim()}>
          Send
        </Button>
      </div>
    </div>
  );
}
