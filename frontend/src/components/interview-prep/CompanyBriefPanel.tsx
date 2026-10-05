// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import type {
  CompanyBrief
} from "@/lib/types/interview-prep";

type Props = {
  brief: CompanyBrief | null;
  paid: boolean;
  unlocking: boolean;
  handleUnlock: () => void;
};

export function CompanyBriefPanel({ brief, paid, unlocking, handleUnlock }: Props) {
  return <>
    {/* Company Brief */}
    {brief && (
      <details className="bg-card border rounded-lg p-4" open>
        <summary className="cursor-pointer font-medium">Company Brief</summary>
        <div className="mt-3 space-y-2 text-sm">
          {brief.mission && (
            <p>
              <strong>Mission:</strong> {brief.mission}
            </p>
          )}
          <p className="text-xs text-muted-foreground">AI-generated company briefing; verify current facts. No live company research is performed.</p>
          {brief.culture && (
            <p>
              <strong>Culture:</strong> {brief.culture}
            </p>
          )}
          {paid ? (
            <>
              {brief.recent_news && (
                <p>
                  <strong>AI-generated context (verify current facts):</strong> {brief.recent_news}
                </p>
              )}
              {brief.things_to_mention.length > 0 && (
                <div>
                  <strong>Things to mention:</strong>
                  <ul className="list-disc pl-5 mt-1">
                    {brief.things_to_mention.map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <div className="mt-2 relative">
              <div className="blur-sm select-none pointer-events-none text-muted-foreground">
                <p>
                  <strong>AI-generated context (verify current facts):</strong> Company background suggestions...
                </p>
                <p className="mt-1">
                  <strong>Things to mention:</strong>
                </p>
                <ul className="list-disc pl-5 mt-1">
                  <li>Key talking points tailored to this role...</li>
                  <li>Specific achievements to highlight...</li>
                </ul>
              </div>
              <div className="absolute inset-0 flex items-center justify-center">
                <button
                  onClick={handleUnlock}
                  disabled={unlocking}
                  className="text-sm font-medium bg-primary text-primary-foreground px-4 py-2 rounded-lg shadow-md hover:bg-primary/90 transition-colors cursor-pointer disabled:opacity-50"
                  title="Costs 1 credit — unlocks full company brief, unlimited questions, and AI coaching for this session"
                >
                  {unlocking ? "Unlocking..." : "Unlock Full Brief — 1 Credit"}
                </button>
              </div>
            </div>
          )}
        </div>
      </details>
    )}

  </>;
}
