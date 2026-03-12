// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "How It Works",
  description:
    "Learn how JobHunter Agent uses AI agents to automate your job search — from discovery to application submission.",
};

const agents = [
  {
    name: "Intake Agent",
    what: "Parses your resume and preferences into a structured search plan.",
    how: "Uses an LLM to extract your skills, experience level, and target roles from raw resume text. Normalizes keywords and expands abbreviations so downstream agents search effectively.",
  },
  {
    name: "Career Coach",
    what: "Rewrites your resume to sell you better and scores it for ATS compatibility.",
    how: "An LLM analyzes keyword density, impact metrics, and formatting. It produces a rewritten resume optimized for applicant tracking systems, plus a cover letter template you can approve or edit.",
  },
  {
    name: "Discovery Agents",
    what: "Search 5+ job boards simultaneously for roles that match your profile.",
    how: "Parallel agents query Indeed, LinkedIn, Glassdoor, ZipRecruiter, and Google Jobs using the Serper search API. Results are deduplicated and normalized into a unified format.",
  },
  {
    name: "Scoring Agent",
    what: "Ranks every discovered job by how well it fits your background.",
    how: "An LLM compares each job description against your resume, scoring on skill match, experience level, location, and salary. Low-fit jobs are filtered out so you only see relevant roles.",
  },
  {
    name: "Resume Tailoring Agent",
    what: "Customizes your resume for each specific role you approve.",
    how: "For every job in your shortlist, an LLM rewrites bullet points to emphasize the skills that job description prioritizes — different emphasis for each application.",
  },
  {
    name: "Application Agent",
    what: "Fills out and submits job applications through a real browser.",
    how: "An AI browser agent navigates to each job posting, fills in application forms with your tailored resume, handles multi-step wizards, file uploads, and custom questions. It operates a real browser — no API shortcuts.",
  },
];

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      {/* Nav */}
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4">
        <div className="mx-auto max-w-4xl flex items-center justify-between">
          <Link href="/" className="text-lg font-bold text-zinc-900 dark:text-white">
            JobHunter Agent
          </Link>
          <Link href="/login">
            <span className="text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-white">
              Log in
            </span>
          </Link>
        </div>
      </nav>

      <main className="mx-auto max-w-4xl px-6 py-16">
        {/* Hero */}
        <div className="mb-12">
          <h1 className="text-4xl font-bold tracking-tight text-zinc-900 dark:text-white">
            How it works
          </h1>
          <p className="mt-4 text-lg text-zinc-600 dark:text-zinc-400 max-w-2xl">
            JobHunter Agent is a multi-agent system. Six specialized AI agents
            collaborate to take you from &ldquo;I need a job&rdquo; to submitted
            applications — each handling one step of the pipeline.
          </p>
        </div>

        {/* Pipeline */}
        <section className="mb-16">
          <div className="space-y-4">
            {agents.map((agent, i) => (
              <div
                key={agent.name}
                className="relative rounded-xl border border-zinc-200 dark:border-zinc-800 p-6"
              >
                <div className="flex items-start gap-4">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 text-sm font-bold">
                    {i + 1}
                  </div>
                  <div>
                    <h3 className="font-semibold text-zinc-900 dark:text-white">
                      {agent.name}
                    </h3>
                    <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                      {agent.what}
                    </p>
                    <p className="mt-2 text-xs text-zinc-500 leading-relaxed">
                      {agent.how}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="text-center rounded-xl border border-zinc-200 dark:border-zinc-800 p-10">
          <h2 className="text-2xl font-semibold text-zinc-900 dark:text-white">
            Ready to try it?
          </h2>
          <p className="mt-2 text-sm text-zinc-500">
            Start with 3 free applications. No credit card required.
          </p>
          <div className="mt-6 flex justify-center gap-4">
            <Link
              href="/register"
              className="inline-flex h-10 items-center rounded-lg bg-blue-600 px-6 text-sm font-medium text-white hover:bg-blue-700"
            >
              Get started
            </Link>
            <Link
              href="/quick-apply"
              className="inline-flex h-10 items-center rounded-lg border border-zinc-300 dark:border-zinc-700 px-6 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-900"
            >
              Quick Apply
            </Link>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-200 px-6 py-10 dark:border-zinc-800">
        <div className="mx-auto max-w-4xl flex flex-col items-center justify-between gap-4 md:flex-row">
          <p className="text-xs text-zinc-500">
            &copy; {new Date().getFullYear()} V2 Software LLC. All rights reserved.
          </p>
          <div className="flex gap-6 text-sm text-zinc-500">
            <Link href="/terms" className="hover:text-zinc-900 dark:hover:text-white">
              Terms
            </Link>
            <Link href="/privacy" className="hover:text-zinc-900 dark:hover:text-white">
              Privacy
            </Link>
            <Link href="/" className="hover:text-zinc-900 dark:hover:text-white">
              Home
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
