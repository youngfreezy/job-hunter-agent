// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import Link from "next/link";


export function InfrastructureSection() {
  return (<>
    {/* Infrastructure & Reliability */}
    <section className="px-6 py-20 bg-white dark:bg-zinc-900/50">
      <div className="mx-auto max-w-6xl">
        <h2 className="mb-4 text-center text-3xl font-bold">Application Infrastructure</h2>
        <p className="mb-10 text-center text-zinc-600 dark:text-zinc-400">
          A hosted application with saved run state, browser visibility, and service health checks.
        </p>
        <div className="grid gap-6 sm:grid-cols-2 md:grid-cols-3">
          <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-6 dark:border-zinc-800 dark:bg-zinc-950">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-100 dark:bg-emerald-950/40">
              <svg
                className="h-5 w-5 text-emerald-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <p className="font-semibold text-zinc-900 dark:text-white">Public Service Status</p>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Check API, database, and queue availability on our{" "}
              <Link
                href="/status"
                className="underline hover:text-zinc-700 dark:hover:text-zinc-300"
              >
                public status page
              </Link>
              .
            </p>
          </div>
          <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-6 dark:border-zinc-800 dark:bg-zinc-950">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 dark:bg-blue-950/40">
              <svg
                className="h-5 w-5 text-blue-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5"
                />
              </svg>
            </div>
            <p className="font-semibold text-zinc-900 dark:text-white">Real-Time Monitoring</p>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Sentry error tracking, structured logging, and dedicated health check endpoints
              (/health, /health/ready) for proactive issue detection.
            </p>
          </div>
          <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-6 dark:border-zinc-800 dark:bg-zinc-950">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-secondary dark:bg-secondary">
              <svg
                className="h-5 w-5 text-foreground"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182M7.875 18.75v-4.992"
                />
              </svg>
            </div>
            <p className="font-semibold text-zinc-900 dark:text-white">
              Recorded Run Outcomes
            </p>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Submitted, failed, and uncertain outcomes are tracked separately. An uncertain
              submission requires checking before another attempt.
            </p>
          </div>
          <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-6 dark:border-zinc-800 dark:bg-zinc-950">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-orange-100 dark:bg-orange-950/40">
              <svg
                className="h-5 w-5 text-orange-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z"
                />
              </svg>
            </div>
            <p className="font-semibold text-zinc-900 dark:text-white">
              Hosted Services
            </p>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Containerized services on Railway use PostgreSQL and Redis for application data
              and orchestration.
            </p>
          </div>
          <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-6 dark:border-zinc-800 dark:bg-zinc-950">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-100 dark:bg-emerald-950/40">
              <svg
                className="h-5 w-5 text-emerald-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z"
                />
              </svg>
            </div>
            <p className="font-semibold text-zinc-900 dark:text-white">Health Check Endpoints</p>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Liveness (/health) and readiness (/health/ready) probes verify API, PostgreSQL, and
              Redis connectivity every 30 seconds.
            </p>
          </div>
          <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-6 dark:border-zinc-800 dark:bg-zinc-950">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-red-100 dark:bg-red-950/40">
              <svg
                className="h-5 w-5 text-red-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"
                />
              </svg>
            </div>
            <p className="font-semibold text-zinc-900 dark:text-white">Security Headers</p>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              HSTS with 1-year max-age, X-Frame-Options DENY, X-Content-Type-Options nosniff,
              strict Referrer-Policy, and restrictive Permissions-Policy.
            </p>
          </div>
        </div>
      </div>
    </section>

  </>);
}
