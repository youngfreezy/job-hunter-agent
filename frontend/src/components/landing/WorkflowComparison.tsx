// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { Card, CardContent } from "@/components/ui/card";


export function WorkflowComparison() {
  return (<>
    {/* Before / After comparison */}
    <section className="px-6 pb-16">
      <div className="mx-auto max-w-4xl">
        <h2 className="mb-8 text-center text-2xl font-bold">The old way vs. the JobHunter way</h2>
        <div className="grid gap-6 md:grid-cols-2">
          <Card className="rounded-3xl border-red-200/60 bg-red-50/50 dark:border-red-900/40 dark:bg-red-950/20">
            <CardContent className="p-6">
              <p className="mb-4 text-sm font-semibold text-red-700 dark:text-red-400">
                Manual Job Search
              </p>
              <ul className="space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 text-red-500">&#10005;</span>Repeatedly copying information
                  into forms
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 text-red-500">&#10005;</span>Same generic resume sent
                  everywhere
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 text-red-500">&#10005;</span>Skip cover letters because
                  they take too long
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 text-red-500">&#10005;</span>Lose track of what you
                  applied to
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 text-red-500">&#10005;</span>Burnout before you get
                  callbacks
                </li>
              </ul>
            </CardContent>
          </Card>
          <Card className="rounded-3xl border-emerald-200/60 bg-emerald-50/50 dark:border-emerald-900/40 dark:bg-emerald-950/20">
            <CardContent className="p-6">
              <p className="mb-4 text-sm font-semibold text-emerald-700 dark:text-emerald-400">
                With JobHunter Agent
              </p>
              <ul className="space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 text-emerald-600">&#10003;</span>Prompt-driven setup with
                  visible browser execution
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 text-emerald-600">&#10003;</span>Resume tailored per
                  role automatically
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 text-emerald-600">&#10003;</span>Custom cover letter for
                  every application
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 text-emerald-600">&#10003;</span>Application log with
                  recorded outcomes
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 text-emerald-600">&#10003;</span>Required questions surfaced
                  in the app
                </li>
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>

  </>);
}
