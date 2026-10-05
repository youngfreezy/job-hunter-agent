// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { Button } from "@/components/ui/button";
import type {
  CoachingHints,
  Grade,
  Question
} from "@/lib/types/interview-prep";

import { InterviewCoaching } from "./InterviewCoaching";

type Props = {
  q: Question | undefined;
  status: string;
  currentQ: number;
  questions: Question[];
  paid: boolean;
  maxFreeQuestions: number;
  coaching: Record<string, CoachingHints>;
  setCoaching: React.Dispatch<React.SetStateAction<Record<string, CoachingHints>>>;
  coachingLoading: boolean;
  handleGetCoaching: () => void;
  showPaywall: boolean;
  unlocking: boolean;
  handleUnlock: () => void;
  onBuyCredits: () => void;
  walletBalance: number | null;
  grades: Grade[];
  handleEnd: () => void;
  answer: string;
  setAnswer: (answer: string) => void;
  handleSubmitAnswer: () => void;
  submitting: boolean;
  handleSkipQuestion: () => void;
};

export function InterviewQuestion({ q, status, currentQ, questions, paid, maxFreeQuestions, coaching, setCoaching, coachingLoading, handleGetCoaching, showPaywall, unlocking, handleUnlock, onBuyCredits, walletBalance, grades, handleEnd, answer, setAnswer, handleSubmitAnswer, submitting, handleSkipQuestion }: Props) {
  return <>
    {/* Question + Answer */}
    {q && status !== "completed" && (
      <div className="bg-card border rounded-lg p-6 space-y-4">
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Q{currentQ + 1} of {questions.length}
          </span>
          <div className="flex items-center gap-3">
            {!paid && currentQ < maxFreeQuestions && (
              <span className="text-xs text-yellow-400">
                {maxFreeQuestions - currentQ - 1} free question
                {maxFreeQuestions - currentQ - 1 !== 1 ? "s" : ""} left
              </span>
            )}
            <span className="capitalize">{q.category.replace("_", " ")}</span>
          </div>
        </div>
        <p className="text-lg font-medium">{q.question}</p>

        <InterviewCoaching q={q} coaching={coaching} setCoaching={setCoaching} coachingLoading={coachingLoading} handleGetCoaching={handleGetCoaching} />

        {showPaywall ? (
          <div className="border-2 border-primary/30 rounded-lg p-6 text-center space-y-4">
            <div className="text-3xl">&#128170;</div>
            <h3 className="text-lg font-semibold">
              You&apos;re doing great! Continue practicing?
            </h3>
            <p className="text-sm text-muted-foreground">
              You&apos;ve used your {maxFreeQuestions} free questions. Unlock unlimited questions
              and coaching for the rest of this session.
            </p>
            <div className="flex items-center justify-center gap-3">
              <Button onClick={handleUnlock} loading={unlocking} size="lg">
                Unlock for 1 Credit
              </Button>
              <Button variant="outline" size="lg" onClick={onBuyCredits}>
                Buy Credits
              </Button>
            </div>
            {walletBalance !== null && (
              <p className="text-xs text-muted-foreground">
                Current balance: {walletBalance} credit{walletBalance !== 1 ? "s" : ""}
              </p>
            )}
            {grades.length > 0 && (
              <button
                onClick={handleEnd}
                className="text-sm text-muted-foreground hover:text-foreground underline"
              >
                Or end session and see your report
              </button>
            )}
          </div>
        ) : (
          <>
            <textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Type your answer..."
              rows={5}
              className="w-full border rounded px-3 py-2 bg-background text-sm resize-y"
            />

            <div className="flex gap-3">
              <Button onClick={handleSubmitAnswer} disabled={submitting || !answer.trim()}>
                {submitting ? "Grading..." : "Submit Answer"}
              </Button>
              <Button
                variant="outline"
                onClick={handleSkipQuestion}
              >
                Skip
              </Button>
              {grades.length > 0 && (
                <Button variant="secondary" onClick={handleEnd}>
                  End & See Report
                </Button>
              )}
            </div>
          </>
        )}
      </div>
    )}

  </>;
}
