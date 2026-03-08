// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useState } from "react";
import { SessionWizard } from "@/components/wizard/SessionWizard";
import { QuickStartForm } from "@/components/wizard/QuickStartForm";

export default function NewSession() {
  const [mode, setMode] = useState<"quick" | "advanced">("quick");

  return (
      <div className="max-w-4xl mx-auto px-6 py-12">
        <div className="mb-8 grid gap-4 rounded-3xl border border-zinc-200 bg-zinc-50 p-6 dark:border-zinc-800 dark:bg-zinc-900/60 md:grid-cols-[1.15fr_0.85fr]">
          <div>
            <h1 className="text-3xl font-bold mb-2">New Session</h1>
            <p className="text-zinc-600 dark:text-zinc-400">
              {mode === "quick"
                ? "Upload your resume and we\u2019ll handle the rest. One click to launch."
                : "Choose your own keywords, locations, and settings. Full control over every detail."}
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
                {mode === "quick"
                  ? "Just your latest resume. We\u2019ll extract everything else."
                  : "Your resume, target job titles, and any preferences for boards or tailoring quality."}
              </p>
            </div>
          </div>
        </div>

        {/* Mode toggle */}
        <div className="mb-6 flex items-center gap-1 rounded-xl bg-zinc-100 p-1 dark:bg-zinc-900">
          <button
            type="button"
            onClick={() => setMode("quick")}
            className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              mode === "quick"
                ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-800 dark:text-white"
                : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
            }`}
          >
            Quick Start
          </button>
          <button
            type="button"
            onClick={() => setMode("advanced")}
            className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              mode === "advanced"
                ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-800 dark:text-white"
                : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
            }`}
          >
            Custom Search
          </button>
        </div>

        {mode === "quick" ? <QuickStartForm /> : <SessionWizard />}
      </div>
  );
}
