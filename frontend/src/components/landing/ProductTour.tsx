// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import Link from "next/link";


export function ProductTour() {
  return (<>
    {/* Product Tour — Interactive Demo */}
    <section id="product-tour" className="px-6 py-20">
      <div className="mx-auto max-w-6xl">
        <h2 className="mb-4 text-center text-3xl font-bold">
          See inside the platform — no signup required
        </h2>
        <p className="mb-12 text-center text-zinc-600 dark:text-zinc-400">
          Illustrative interface examples with sample data. For recorded app footage, watch the {" "}<Link href="/demo" className="underline">product demo</Link>.
        </p>
        <div className="grid gap-6 md:grid-cols-2">
          {/* Card 1: AI Career Coach */}
          <div className="rounded-3xl border border-zinc-200/80 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden">
            <div className="flex items-center gap-1.5 bg-zinc-100 px-4 py-2.5 dark:bg-zinc-900">
              <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
              <span className="ml-2 text-xs text-zinc-500">AI Career Coach</span>
            </div>
            <div className="p-5">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="font-semibold text-zinc-900 dark:text-white">Resume Analysis</h3>
                <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-bold text-blue-700 dark:bg-blue-950 dark:text-blue-300">
                  Score: 87/100
                </span>
              </div>
              <div className="mb-4 grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-lg bg-emerald-50 p-2 dark:bg-emerald-950/30">
                  <p className="font-bold text-emerald-700 dark:text-emerald-300">9.2</p>
                  <p className="text-zinc-500">Impact</p>
                </div>
                <div className="rounded-lg bg-blue-50 p-2 dark:bg-blue-950/30">
                  <p className="font-bold text-blue-700 dark:text-blue-300">8.5</p>
                  <p className="text-zinc-500">Clarity</p>
                </div>
                <div className="rounded-lg bg-secondary p-2 dark:bg-secondary">
                  <p className="font-bold text-foreground dark:text-foreground">8.8</p>
                  <p className="text-zinc-500">Keywords</p>
                </div>
              </div>
              <ul className="space-y-1.5 text-xs text-zinc-600 dark:text-zinc-400">
                <li className="flex items-start gap-1.5">
                  <span className="text-emerald-600">&#10003;</span> Added 4 quantified
                  achievements to experience section
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="text-emerald-600">&#10003;</span> Optimized for ATS keyword
                  matching (12 keywords added)
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="text-emerald-600">&#10003;</span> Custom cover letter template
                  generated
                </li>
              </ul>
            </div>
          </div>

          {/* Card 2: Smart Job Matching */}
          <div className="rounded-3xl border border-zinc-200/80 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden">
            <div className="flex items-center gap-1.5 bg-zinc-100 px-4 py-2.5 dark:bg-zinc-900">
              <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
              <span className="ml-2 text-xs text-zinc-500">
                Job Shortlist — Approval Checkpoint
              </span>
            </div>
            <div className="p-5">
              <div className="mb-3 rounded-xl border border-zinc-200 p-3 dark:border-zinc-700">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="text-sm font-semibold text-zinc-900 dark:text-white">
                      Senior Frontend Engineer
                    </p>
                    <p className="text-xs text-zinc-500">
                      Stripe &middot; San Francisco, CA &middot; $185k-$245k
                    </p>
                  </div>
                  <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-bold text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                    92% Match
                  </span>
                </div>
                <div className="flex gap-2">
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                    React
                  </span>
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                    TypeScript
                  </span>
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                    Remote OK
                  </span>
                </div>
              </div>
              <div className="rounded-xl border border-zinc-200 p-3 dark:border-zinc-700">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="text-sm font-semibold text-zinc-900 dark:text-white">
                      Full Stack Developer
                    </p>
                    <p className="text-xs text-zinc-500">
                      Notion &middot; New York, NY &middot; $160k-$210k
                    </p>
                  </div>
                  <span className="rounded-full bg-blue-100 px-2.5 py-1 text-xs font-bold text-blue-700 dark:bg-blue-950 dark:text-blue-300">
                    85% Match
                  </span>
                </div>
                <div className="flex gap-2">
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                    Node.js
                  </span>
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                    PostgreSQL
                  </span>
                </div>
              </div>
              <div className="mt-3 flex gap-2 justify-end">
                <span className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-600 dark:border-zinc-600 dark:text-zinc-400">
                  Skip
                </span>
                <span className="rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white dark:bg-white dark:text-zinc-900">
                  Approve &amp; Apply
                </span>
              </div>
            </div>
          </div>

          {/* Card 3: Live Browser Feed */}
          <div className="rounded-3xl border border-zinc-200/80 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden">
            <div className="flex items-center gap-1.5 bg-zinc-100 px-4 py-2.5 dark:bg-zinc-900">
              <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
              <span className="ml-2 text-xs text-zinc-500">
                Live Browser — Applying to Stripe
              </span>
              <span className="ml-auto flex items-center gap-1 text-xs text-emerald-600">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Live
              </span>
            </div>
            <div className="p-5">
              <div className="mb-3 rounded-lg bg-zinc-50 p-3 dark:bg-zinc-900">
                <div className="mb-2 flex items-center justify-between text-xs">
                  <span className="text-zinc-500">Progress</span>
                  <span className="font-medium text-zinc-900 dark:text-white">Step 3 of 5</span>
                </div>
                <div className="h-2 rounded-full bg-zinc-200 dark:bg-zinc-700">
                  <div className="h-2 w-3/5 rounded-full bg-emerald-500" />
                </div>
              </div>
              <div className="space-y-2 text-xs text-zinc-600 dark:text-zinc-400">
                <div className="flex items-center gap-2">
                  <span className="text-emerald-600">&#10003;</span> Navigated to Stripe careers
                  page
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-emerald-600">&#10003;</span> Found &quot;Senior Frontend
                  Engineer&quot; listing
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-blue-600">&#9654;</span> Filling application form (field 8
                  of 14)
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-zinc-400">&#9679;</span> Upload tailored resume
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-zinc-400">&#9679;</span> Submit and capture confirmation
                </div>
              </div>
            </div>
          </div>

          {/* Card 4: Results Dashboard */}
          <div className="rounded-3xl border border-zinc-200/80 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden">
            <div className="flex items-center gap-1.5 bg-zinc-100 px-4 py-2.5 dark:bg-zinc-900">
              <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
              <span className="ml-2 text-xs text-zinc-500">Results Dashboard</span>
            </div>
            <div className="p-5">
              <div className="mb-4 grid grid-cols-3 gap-3 text-center">
                <div className="rounded-xl bg-emerald-50 p-3 dark:bg-emerald-950/30">
                  <p className="text-xl font-bold text-emerald-700 dark:text-emerald-300">47</p>
                  <p className="text-xs text-zinc-500">Submitted</p>
                </div>
                <div className="rounded-xl bg-blue-50 p-3 dark:bg-blue-950/30">
                  <p className="text-xl font-bold text-blue-700 dark:text-blue-300">12</p>
                  <p className="text-xs text-zinc-500">Callbacks</p>
                </div>
                <div className="rounded-xl bg-secondary p-3 dark:bg-secondary">
                  <p className="text-xl font-bold text-foreground dark:text-foreground">26%</p>
                  <p className="text-xs text-zinc-500">Success Rate</p>
                </div>
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between rounded-lg border border-zinc-200 px-3 py-2 text-xs dark:border-zinc-700">
                  <span className="text-zinc-700 dark:text-zinc-300">
                    Stripe — Senior Frontend Eng.
                  </span>
                  <span className="rounded bg-emerald-100 px-2 py-0.5 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                    Interview
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-zinc-200 px-3 py-2 text-xs dark:border-zinc-700">
                  <span className="text-zinc-700 dark:text-zinc-300">
                    Notion — Full Stack Developer
                  </span>
                  <span className="rounded bg-blue-100 px-2 py-0.5 text-blue-700 dark:bg-blue-950 dark:text-blue-300">
                    Applied
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-zinc-200 px-3 py-2 text-xs dark:border-zinc-700">
                  <span className="text-zinc-700 dark:text-zinc-300">
                    Vercel — Frontend Engineer
                  </span>
                  <span className="rounded bg-yellow-100 px-2 py-0.5 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300">
                    Callback
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

  </>);
}
