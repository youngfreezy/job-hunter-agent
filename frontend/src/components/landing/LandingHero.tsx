// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { indeedEasyApplyOnly } from "@/lib/indeed-policy";
import Link from "next/link";


export function LandingHero() {
  return (<>
    {/* Hero */}
    <section className="px-6 py-10">
      <div className="mx-auto max-w-7xl">
        <div className="relative overflow-hidden rounded-[36px] border border-zinc-200/80 bg-white px-8 py-10 shadow-[0_24px_80px_-36px_rgba(15,23,42,0.35)] dark:border-zinc-800 dark:bg-zinc-950 lg:px-12 lg:py-12">
          <div className="absolute -left-24 top-10 h-64 w-64 rounded-full bg-blue-200/40 blur-3xl dark:bg-primary/10" />
          <div className="absolute right-0 top-0 h-80 w-80 rounded-full bg-emerald-200/35 blur-3xl dark:bg-emerald-500/10" />
          <div className="relative mx-auto max-w-3xl text-center">
            <Badge
              variant="secondary"
              className="mb-5 bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
            >
              You approve everything before it goes out
            </Badge>
            <h1 className="text-5xl font-bold tracking-tight text-zinc-950 dark:text-white md:text-6xl">
              Land more interviews
              <br />
              while saving 15+ hours a week.
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-zinc-600 dark:text-zinc-400">
              Your AI assistant finds roles {indeedEasyApplyOnly ? "on Indeed" : "across 5 job boards"}, tailors your resume for
              each one, and submits applications automatically. You stay in complete control with
              two approval checkpoints.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Link href="/try">
                <Button
                  size="lg"
                  data-umami-event="cta-try-free"
                  data-umami-event-location="hero"
                >
                  Try Free with Google
                </Button>
              </Link>
              <Link href="/session/new">
                <Button
                  size="lg"
                  variant="outline"
                  data-umami-event="cta-get-started"
                  data-umami-event-location="hero"
                >
                  Sign In to Start
                </Button>
              </Link>
            </div>
            <Link
              href="/demo"
              className="mt-5 inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-medium text-zinc-700 underline underline-offset-4 hover:text-zinc-950 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 dark:text-zinc-300 dark:hover:text-white"
            >
              Watch the product demo →
            </Link>
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              Sign in with Google and connect your Anthropic and Browserbase API keys. Provider usage is billed separately.
            </p>
            <p className="mt-1 text-sm text-zinc-400 dark:text-zinc-500">
              Already have jobs in mind?{" "}
              <Link
                href="/quick-apply"
                className="underline hover:text-zinc-700 dark:hover:text-zinc-300"
              >
                Paste URLs and apply instantly
              </Link>
              .
            </p>
            <p className="mt-1 text-sm text-zinc-400 dark:text-zinc-500">
              Or{" "}
              <a
                href="#product-tour"
                className="underline hover:text-zinc-700 dark:hover:text-zinc-300"
              >
                explore the product tour below
              </a>{" "}
              — no account needed.
            </p>

            {/* Stats bar */}
            <div className="mt-10 grid gap-6 sm:grid-cols-3">
              {[
                { value: indeedEasyApplyOnly ? "Indeed Easy Apply" : "5 job boards", label: indeedEasyApplyOnly ? "Focused job discovery" : "Searched simultaneously" },
                { value: "3 free credits", label: "Then from $2.00/app" },
                { value: "2 approval steps", label: "You control everything" },
              ].map((s) => (
                <div key={s.value}>
                  <p className="text-2xl font-bold text-zinc-900 dark:text-white">{s.value}</p>
                  <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{s.label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>

  </>);
}
