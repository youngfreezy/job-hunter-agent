// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { Button } from "@/components/ui/button";
import type {
  CoachingHints,
  Question
} from "@/lib/types/interview-prep";

type Props = {
  q: Question;
  coaching: Record<string, CoachingHints>;
  setCoaching: React.Dispatch<React.SetStateAction<Record<string, CoachingHints>>>;
  coachingLoading: boolean;
  handleGetCoaching: () => void;
};
export function InterviewCoaching({ q, coaching, setCoaching, coachingLoading, handleGetCoaching }: Props) {
  return <>
    {/* Coaching hints */}
    {!coaching[q.id] && (
      <Button
        variant="outline"
        size="sm"
        onClick={handleGetCoaching}
        disabled={coachingLoading}
        className="text-blue-400 border-primary/30 hover:bg-primary/10"
      >
        {coachingLoading ? (
          <>
            <span className="animate-spin h-3.5 w-3.5 border-2 border-blue-400 border-t-transparent rounded-full mr-2" />
            Analyzing your resume...
          </>
        ) : (
          "Get AI Coaching"
        )}
      </Button>
    )}

    {coaching[q.id] && (
      <div className="border border-primary/30 bg-primary/5 rounded-lg p-4 space-y-3 text-sm">
        <div className="flex items-center justify-between">
          <span className="font-medium text-blue-400">AI Coach</span>
          <button
            onClick={() =>
              setCoaching((prev) => {
                const next = { ...prev };
                delete next[q.id];
                return next;
              })
            }
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Hide
          </button>
        </div>

        {coaching[q.id].resume_highlights.length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-1">
              From your resume:
            </p>
            <ul className="space-y-1">
              {coaching[q.id].resume_highlights.map((h, i) => (
                <li
                  key={i}
                  className="text-muted-foreground pl-3 border-l-2 border-primary/30"
                >
                  {h}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1">
            Structure your answer (Situation, Task, Action, Result):
          </p>
          <div className="grid grid-cols-1 gap-1.5">
            {(["situation", "task", "action", "result"] as const).map((key) => (
              <div key={key} className="flex gap-2">
                <span className="font-semibold text-blue-400 uppercase text-xs w-16 shrink-0 pt-0.5">
                  {key[0]}
                </span>
                <span className="text-muted-foreground">
                  {coaching[q.id].star_scaffold[key]}
                </span>
              </div>
            ))}
          </div>
        </div>

        {coaching[q.id].key_points.length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-1">
              What they want to hear:
            </p>
            <div className="flex flex-wrap gap-1.5">
              {coaching[q.id].key_points.map((p, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 bg-primary/10 text-blue-300 text-xs rounded-full border border-primary/20"
                >
                  {p}
                </span>
              ))}
            </div>
          </div>
        )}

        {coaching[q.id].pitfalls.length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-1">Avoid:</p>
            <ul className="space-y-0.5">
              {coaching[q.id].pitfalls.map((p, i) => (
                <li key={i} className="text-yellow-400/80 text-xs">
                  &#x26A0; {p}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    )}

  </>;
}
