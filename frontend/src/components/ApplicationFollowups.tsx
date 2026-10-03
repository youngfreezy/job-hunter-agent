import Link from "next/link";

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

export function ApplicationFollowups({ questions = {}, employers = {} }: {
  questions?: Record<string, ApplicationQuestion>;
  employers?: Record<string, EmployerApplication>;
}) {
  const pending = Object.entries(employers).filter(([, item]) => item.status === "queued");
  const unanswered = Object.entries(questions);
  if (!pending.length && !unanswered.length) return null;
  return <section className="space-y-4 rounded-xl border border-border p-4" aria-label="Application follow-ups">
    {pending.length > 0 && <div>
      <h2 className="text-sm font-semibold">Employer applications queued ({pending.length})</h2>
      <p className="mt-1 text-xs text-muted-foreground">Found on Indeed. These run after the Indeed forms.</p>
      <ul className="mt-2 space-y-2 text-sm">{pending.map(([id, job]) => <li key={id}>{job.title} · {job.company}</li>)}</ul>
    </div>}
    {unanswered.length > 0 && <div>
      <h2 className="text-sm font-semibold">Needs your answer ({unanswered.length})</h2>
      <ul className="mt-2 space-y-3 text-sm">{unanswered.map(([id, job]) => <li key={id}>
        <p className="font-medium">{job.title} · {job.company}</p>
        <p className="mt-1 text-muted-foreground">{job.question}</p>
        <a className="mt-1 inline-block underline underline-offset-4" href={job.source_url} target="_blank" rel="noopener noreferrer">Original Indeed listing</a>
      </li>)}</ul>
      <p className="mt-3 text-xs text-muted-foreground">Save the missing facts in <Link className="underline" href="/settings">application rules</Link>, then retry the listing through <Link className="underline" href="/quick-apply">Quick Apply</Link>. No application was submitted for these questions.</p>
    </div>}
  </section>;
}
