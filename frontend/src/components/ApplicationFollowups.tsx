"use client";

import { useId, useState } from "react";
import Link from "next/link";
import { quickApplyRetryHref, savedApplicationAnswer } from "@/lib/applicationAnswers";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export type ApplicationQuestion = {
  question: string;
  title: string;
  company: string;
  source_url: string;
  application_url: string;
};
export type EmployerApplication = {
  title: string;
  company: string;
  source_url: string;
  url: string;
  status: string;
};
export type AnswerApplicationQuestion = (jobId: string, answer: string) => Promise<{ message?: string }>;

function QuestionCard({ jobId, job, onAnswer, persistedAnswer }: {
  jobId: string;
  job: ApplicationQuestion;
  onAnswer?: AnswerApplicationQuestion;
  persistedAnswer: string | null;
}) {
  const fieldId = useId();
  const [answer, setAnswer] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const retryHref = quickApplyRetryHref(job.source_url);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!onAnswer || !answer.trim() || saving) return;
    setSaving(true);
    setError(null);
    try {
      const result = await onAnswer(jobId, answer.trim());
      setSaved(result.message || "Answer saved in Settings for this company and question. It will be used on your next attempt.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save your answer. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return <li className="rounded-lg border border-border bg-card p-3">
    <p className="font-medium">{job.title} · {job.company}</p>
    <p id={`${fieldId}-question`} className="mt-1 text-sm text-foreground">{job.question}</p>
    <a className="mt-1 inline-block text-xs underline underline-offset-4" href={job.source_url} target="_blank" rel="noopener noreferrer">Original Indeed listing</a>
    {saved || persistedAnswer !== null ? <div className="mt-3 space-y-2">
      <p className="text-sm" role="status">{saved || "Answer saved in Settings for this company and question."}</p>
      {persistedAnswer !== null && <p className="whitespace-pre-wrap text-sm text-muted-foreground">Your answer: {persistedAnswer}</p>}
      {retryHref ? <><Button asChild size="sm"><Link href={retryHref}>Retry this job</Link></Button><p className="text-xs text-muted-foreground">Review this one job in Quick Apply, then press Apply to start a new attempt. Saving an answer does not restart this run.</p></> : <p className="text-xs text-muted-foreground">Open Quick Apply and paste the original Indeed listing to retry.</p>}
    </div> : onAnswer && <form onSubmit={submit} className="mt-3 space-y-2">
      <label htmlFor={fieldId} className="block text-sm font-medium">Your answer</label>
      <Textarea id={fieldId} value={answer} onChange={(event) => setAnswer(event.target.value)} required maxLength={4000} disabled={saving} aria-describedby={`${fieldId}-question ${fieldId}-error`} placeholder="Enter the answer you want used for this application." />
      <p id={`${fieldId}-error`} className="text-xs text-destructive empty:hidden" role="alert">{error}</p>
      <Button type="submit" size="sm" loading={saving} disabled={!answer.trim() || saving}>Save answer</Button>
    </form>}
  </li>;
}

export function ApplicationFollowups({ questions = {}, employers = {}, onAnswer, savedRules = "" }: {
  questions?: Record<string, ApplicationQuestion>;
  employers?: Record<string, EmployerApplication>;
  onAnswer?: AnswerApplicationQuestion;
  savedRules?: string;
}) {
  const pending = Object.entries(employers).filter(([, item]) => item.status === "queued");
  const unanswered = Object.entries(questions);
  const needsAnswerCount = unanswered.filter(([, job]) => savedApplicationAnswer(savedRules, job) === null).length;
  if (!pending.length && !unanswered.length) return null;
  return <section className="space-y-4 rounded-xl border border-border p-4" aria-label="Application follow-ups">
    {unanswered.length > 0 && <div>
      <h2 className="text-base font-semibold">{needsAnswerCount ? `Needs your answer (${needsAnswerCount})` : "Answers saved · ready to retry"}</h2>
      <p className="mt-1 text-xs text-muted-foreground">These applications stopped for a question. Other eligible jobs can continue. Save any missing answers below, then explicitly retry each job when you are ready.</p>
      <ul className="mt-3 space-y-3">{unanswered.map(([id, job]) => <QuestionCard key={`${id}:${job.question}`} jobId={id} job={job} onAnswer={onAnswer} persistedAnswer={savedApplicationAnswer(savedRules, job)} />)}</ul>
    </div>}
    {pending.length > 0 && <div>
      <h2 className="text-sm font-semibold">Employer applications queued ({pending.length})</h2>
      <p className="mt-1 text-xs text-muted-foreground">Found on Indeed. These run after the Indeed forms.</p>
      <ul className="mt-2 space-y-2 text-sm">{pending.map(([id, job]) => <li key={id}>{job.title} · {job.company}</li>)}</ul>
    </div>}
  </section>;
}
