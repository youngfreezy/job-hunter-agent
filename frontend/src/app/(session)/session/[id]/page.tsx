"use client";
import { ApplicationFollowups } from "@/components/ApplicationFollowups";
import { LiveBrowserPanel } from "@/components/LiveBrowserPanel";
import { CoachReviewDialog } from "@/components/session/CoachReviewDialog";
import { sessionPresentation } from "@/components/session/presentation";
import { RunActionDialogs } from "@/components/session/RunActionDialogs";
import { SessionActivity } from "@/components/session/SessionActivity";
import { SessionApplications } from "@/components/session/SessionApplications";
import { SessionChat } from "@/components/session/SessionChat";
import { SessionCheckpoints } from "@/components/session/SessionCheckpoints";
import { SessionLoginDialog } from "@/components/session/SessionLoginDialog";
import { SessionNeedsQueue } from "@/components/session/SessionNeedsQueue";
import { SessionParameters } from "@/components/session/SessionParameters";
import { SessionStatus } from "@/components/session/SessionStatus";
import { ShortlistReviewDialog } from "@/components/session/ShortlistReviewDialog";
import { useSessionRun, type LoadedSessionRun } from "@/components/session/use-session-run";
import { useParams } from "next/navigation";

export default function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const run = useSessionRun(id);
  const { session } = run;
  if(!session) {
    return (
      <div className="space-y-5" aria-busy="true">
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex gap-3">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="flex-1 space-y-2">
                <div className="h-3 w-16 rounded bg-muted" />
                <div className="h-5 w-10 rounded bg-muted" />
                <div className="h-1.5 rounded-full bg-muted" />
              </div>
            ))}
          </div>
        </div>
        <div className="h-64 rounded-xl border border-border bg-card" />
      </div>
    );
  }

  return <SessionContent run={{ ...run, session }} />;
}

function SessionContent({ run }: { run: LoadedSessionRun }) {
  const { session, sessionSummary, events, shortlistJobs, elapsedSeconds, interventionData, submitConfirmData, loginPrompt, liveView, liveViewJobLabel, setLiveView, savedAnswerRules, saveAnswer } = run;
  const view = sessionPresentation(session, sessionSummary, events, shortlistJobs, elapsedSeconds, Boolean(interventionData || submitConfirmData || loginPrompt));
  return (
    <>
      <SessionStatus run={run} view={view} />
      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-5">
          {liveView && (
            <LiveBrowserPanel liveView={liveView} jobLabel={liveViewJobLabel} onHide={() => setLiveView(null)} />
          )}

          <ApplicationFollowups questions={session.application_questions} employers={session.employer_application_queue} savedRules={savedAnswerRules} onAnswer={async (jobId, answer) => {
            const question = session.application_questions?.[jobId];
            if(!question) throw new Error("This question is no longer available. Reload the run.");
            await saveAnswer(question, answer);
            return {};
          }} />

          <SessionActivity view={view} />
          <SessionApplications run={run} />
        </div>

        <aside className="min-w-0 space-y-5" aria-label="Run details">
          <SessionNeedsQueue run={run} />
          <SessionParameters run={run} view={view} />
          <SessionChat run={run} view={view} />
          <SessionCheckpoints run={run} view={view} />
        </aside>
      </div>

      <RunActionDialogs run={run} />
      <CoachReviewDialog run={run} />
      <ShortlistReviewDialog run={run} />
      <SessionLoginDialog run={run} />
    </>
  );
}
