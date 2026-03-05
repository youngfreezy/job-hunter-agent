"use client";

import { useEffect, useRef } from "react";
export type StatusEvent = {
  event: string;
  agent: string;
  status: string;
  message: string;
  timestamp: string;
};

const AGENT_COLORS: Record<string, string> = {
  intake: "bg-blue-100 text-blue-800",
  career_coach: "bg-purple-100 text-purple-800",
  discovery: "bg-green-100 text-green-800",
  scoring: "bg-yellow-100 text-yellow-800",
  resume_tailor: "bg-orange-100 text-orange-800",
  application: "bg-red-100 text-red-800",
  verification: "bg-teal-100 text-teal-800",
  reporting: "bg-indigo-100 text-indigo-800",
  system: "bg-zinc-100 text-zinc-800",
};

export function StatusFeed({ events }: { events: StatusEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="space-y-1.5 font-mono text-sm">
      {events.length === 0 && (
        <p className="text-zinc-400 text-center py-8">
          Waiting for agent activity...
        </p>
      )}
      {events.map((evt, i) => (
        <div key={i} className="flex items-start gap-2 py-0.5">
          <span className="text-zinc-400 text-xs whitespace-nowrap mt-0.5">
            {new Date(evt.timestamp).toLocaleTimeString()}
          </span>
          <span
            className={`text-xs px-1.5 py-0.5 rounded font-medium whitespace-nowrap ${
              AGENT_COLORS[evt.agent] || AGENT_COLORS.system
            }`}
          >
            {evt.agent}
          </span>
          <span
            className={
              evt.event === "error"
                ? "text-red-500"
                : "text-zinc-700 dark:text-zinc-300"
            }
          >
            {evt.message}
          </span>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
