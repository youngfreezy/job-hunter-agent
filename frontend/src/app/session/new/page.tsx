"use client";

import Link from "next/link";
import { SessionWizard } from "@/components/wizard/SessionWizard";

export default function NewSession() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4 flex items-center justify-between max-w-7xl mx-auto">
        <Link href="/" className="text-xl font-bold tracking-tight">JobHunter Agent</Link>
        <Link href="/dashboard" className="text-sm text-zinc-600 dark:text-zinc-400 hover:text-zinc-900">
          Dashboard
        </Link>
      </nav>

      <div className="max-w-2xl mx-auto px-6 py-12">
        <h1 className="text-3xl font-bold mb-2">New Session</h1>
        <p className="text-zinc-600 dark:text-zinc-400 mb-8">
          Configure your job search. The AI will coach your resume, discover jobs, and apply for you.
        </p>

        <SessionWizard />
      </div>
    </div>
  );
}
