"use client";

import Link from "next/link";
import { SessionWizard } from "@/components/wizard/SessionWizard";

export default function NewSession() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4 flex items-center justify-between max-w-7xl mx-auto">
        <Link href="/" className="text-xl font-bold tracking-tight">
          JobHunter Agent
        </Link>
        <Link
          href="/dashboard"
          className="text-sm text-zinc-600 dark:text-zinc-400 hover:text-zinc-900"
        >
          Dashboard
        </Link>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-12">
        <div className="mb-8 grid gap-4 rounded-3xl border border-zinc-200 bg-zinc-50 p-6 dark:border-zinc-800 dark:bg-zinc-900/60 md:grid-cols-[1.15fr_0.85fr]">
          <div>
            <h1 className="text-3xl font-bold mb-2">New Session</h1>
            <p className="text-zinc-600 dark:text-zinc-400">
              Set up your search in a few minutes. We&apos;ll coach your resume, find the best matches, and only apply after you give the green light.
            </p>
          </div>
          <div className="grid gap-3 text-sm">
            <div className="rounded-2xl bg-white p-4 dark:bg-zinc-950/70">
              <p className="font-medium">What to expect</p>
              <p className="mt-1 text-zinc-600 dark:text-zinc-400">
                First we improve your resume, then we find and rank jobs, and finally we apply — with your approval at every step.
              </p>
            </div>
            <div className="rounded-2xl bg-white p-4 dark:bg-zinc-950/70">
              <p className="font-medium">What to have ready</p>
              <p className="mt-1 text-zinc-600 dark:text-zinc-400">
                Your latest resume and the job titles or skills you want to search for.
              </p>
            </div>
          </div>
        </div>

        <SessionWizard />
      </div>
    </div>
  );
}
