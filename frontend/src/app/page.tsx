"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type BillingMode = "monthly" | "weekly";

const planCatalog = [
  {
    name: "Free",
    monthlyPrice: 0,
    weeklyPrice: 0,
    capacity: "5 total applications",
    summary: "Validate the workflow before you commit.",
    features: [
      "Session wizard and live job tracking",
      "One coached resume pass",
      "Shortlist review before apply",
      "Manual apply log and proofs",
    ],
    cta: "Start Free",
    popular: false,
  },
  {
    name: "Pro",
    monthlyPrice: 49,
    weeklyPrice: 19,
    capacity: "40 applications per week",
    summary: "The self-serve plan for most active job seekers.",
    features: [
      "Resume coaching, tailoring, and cover letters",
      "Live status feed and shortlist review",
      "Session steering chat to adjust strategy",
      "Manual apply log with tailored artifacts",
    ],
    cta: "Choose Pro",
    popular: true,
  },
  {
    name: "Power",
    monthlyPrice: 99,
    weeklyPrice: 39,
    capacity: "100 applications per week",
    summary: "For users who want live control when ATS sites fight back.",
    features: [
      "Everything in Pro",
      "Screenshot stream during live applications",
      "Browser takeover for CAPTCHA, login, and edge cases",
      "Priority support for blocked runs",
    ],
    cta: "Choose Power",
    popular: false,
  },
];

const steps = [
  {
    num: "1",
    title: "Configure The Search",
    desc: "Set keywords, locations, salary floor, and remote preference so the pipeline starts with constraints that actually matter.",
  },
  {
    num: "2",
    title: "Coach The Resume",
    desc: "The coach rewrites your resume, scores it, drafts a reusable cover letter angle, and pauses for review before mass action.",
  },
  {
    num: "3",
    title: "Rank The Market",
    desc: "Discovery agents scan major boards, score relevance, and build a shortlist you can approve before the apply stage.",
  },
  {
    num: "4",
    title: "Apply With Oversight",
    desc: "Applications stream live. You can steer strategy in chat, intervene when a site blocks, and take direct control when needed.",
  },
  {
    num: "5",
    title: "Audit Every Attempt",
    desc: "Every submitted, skipped, or failed application is logged with the tailored resume and cover letter used for that job.",
  },
  {
    num: "6",
    title: "Recover Fast",
    desc: "Review checkpoints, resume after interruptions, and keep the session moving instead of restarting from scratch.",
  },
];

const differentiators = [
  {
    title: "Live Control When Sites Break",
    body: "Steer in chat, pause the workflow, or take over the browser when login, CAPTCHA, or ambiguous forms show up.",
  },
  {
    title: "Approval Gates Before Scale",
    body: "The system pauses for coached-resume review and shortlist approval so you do not spray low-quality applications.",
  },
  {
    title: "Proof, Not Guesswork",
    body: "The manual apply log stores what happened for each job, including tailored resumes, cover letters, and failure reasons.",
  },
];

export default function Home() {
  const [billingMode, setBillingMode] = useState<BillingMode>("monthly");

  const billingLabel = useMemo(
    () => ({
      monthly: {
        suffix: "/month",
        helper: "Best value for active searches. Monthly is preselected.",
      },
      weekly: {
        suffix: "/week",
        helper: "Use weekly billing if you need a short burst of applications.",
      },
    }),
    []
  );

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <span className="text-xl font-bold tracking-tight">
            JobHunter Agent
          </span>
          <div className="flex items-center gap-4">
            <Link
              href="/dashboard"
              className="text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              Dashboard
            </Link>
            <Link href="/session/new">
              <Button size="sm">Get Started</Button>
            </Link>
          </div>
        </div>
      </nav>

      <section className="px-6 py-20">
        <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
          <div>
            <div className="mb-5 flex flex-wrap gap-2">
              <Badge variant="secondary" className="bg-blue-50 text-blue-700">
                Review gates before mass apply
              </Badge>
              <Badge
                variant="secondary"
                className="bg-emerald-50 text-emerald-700"
              >
                Live takeover when needed
              </Badge>
            </div>
            <h1 className="max-w-4xl text-5xl font-bold tracking-tight text-zinc-950 dark:text-white md:text-6xl">
              Start the search once.
              <br />
              Keep control through every application.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-zinc-600 dark:text-zinc-400">
              JobHunter Agent coaches the resume, discovers roles, scores the
              market, and applies with live oversight. When ATS sites force a
              decision, you can steer in chat or take over the browser instead
              of losing the run.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/session/new">
                <Button size="lg">Start Free</Button>
              </Link>
              <a href="#pricing">
                <Button size="lg" variant="outline">
                  See Pricing
                </Button>
              </a>
            </div>
            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              {differentiators.map((item) => (
                <Card key={item.title} className="border-zinc-200/80">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">{item.title}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-zinc-600 dark:text-zinc-400">
                      {item.body}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>

          <Card className="border-zinc-900 bg-zinc-950 text-white shadow-2xl shadow-zinc-900/20 dark:border-zinc-800">
            <CardHeader className="pb-4">
              <Badge className="w-fit bg-white/10 text-white hover:bg-white/10">
                What a session gives you
              </Badge>
              <CardTitle className="text-2xl">
                Launch once, intervene only when it matters
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-zinc-300">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-zinc-400">
                  Phase 1
                </p>
                <p className="mt-2 font-medium text-white">
                  Coach review blocks low-quality starts
                </p>
                <p className="mt-1 leading-6">
                  You approve the rewritten resume before discovery continues.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-zinc-400">
                  Phase 2
                </p>
                <p className="mt-2 font-medium text-white">
                  Shortlist review controls which jobs get applied to
                </p>
                <p className="mt-1 leading-6">
                  The ranked shortlist pauses for approval instead of silently
                  applying everywhere.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-zinc-400">
                  Phase 3
                </p>
                <p className="mt-2 font-medium text-white">
                  Steering and takeover handle hostile ATS flows
                </p>
                <p className="mt-1 leading-6">
                  Use chat for strategy changes and takeover for login,
                  verification, and form edge cases.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="bg-zinc-50 px-6 py-20 dark:bg-zinc-900">
        <div className="mx-auto max-w-6xl">
          <div className="mb-12 flex items-end justify-between gap-6">
            <div>
              <h2 className="text-3xl font-bold">How It Works</h2>
              <p className="mt-2 max-w-2xl text-zinc-600 dark:text-zinc-400">
                The product is designed around supervised automation, not blind
                one-click spam.
              </p>
            </div>
            <div className="hidden rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-600 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400 md:block">
              Six phases. Two approval gates. Live control when sites resist.
            </div>
          </div>
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
            {steps.map((step) => (
              <Card key={step.num} className="border-zinc-200/80 bg-white/80">
                <CardHeader>
                  <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-full bg-zinc-900 text-sm font-bold text-white dark:bg-white dark:text-zinc-900">
                    {step.num}
                  </div>
                  <CardTitle className="text-lg">{step.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400">
                    {step.desc}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section id="pricing" className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mb-10 flex flex-col items-start justify-between gap-6 lg:flex-row lg:items-end">
            <div>
              <h2 className="text-3xl font-bold">
                Start Free, Upgrade When You Apply at Scale
              </h2>
              <p className="mt-2 max-w-2xl text-zinc-600 dark:text-zinc-400">
                Monthly billing is the default. Power is where screenshot
                streaming, steering, and takeover become part of the workflow.
              </p>
            </div>
            <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-1 dark:border-zinc-800 dark:bg-zinc-900">
              <button
                className={`rounded-xl px-4 py-2 text-sm font-medium transition-colors ${
                  billingMode === "monthly"
                    ? "bg-white text-zinc-950 shadow-sm dark:bg-zinc-950 dark:text-white"
                    : "text-zinc-500"
                }`}
                onClick={() => setBillingMode("monthly")}
                type="button"
              >
                Monthly
              </button>
              <button
                className={`rounded-xl px-4 py-2 text-sm font-medium transition-colors ${
                  billingMode === "weekly"
                    ? "bg-white text-zinc-950 shadow-sm dark:bg-zinc-950 dark:text-white"
                    : "text-zinc-500"
                }`}
                onClick={() => setBillingMode("weekly")}
                type="button"
              >
                Weekly
              </button>
            </div>
          </div>

          <p className="mb-8 text-sm text-zinc-500 dark:text-zinc-400">
            {billingLabel[billingMode].helper}
          </p>

          <div className="grid gap-6 md:grid-cols-3">
            {planCatalog.map((plan) => {
              const price =
                billingMode === "monthly" ? plan.monthlyPrice : plan.weeklyPrice;
              return (
                <Card
                  key={plan.name}
                  className={`relative flex h-full flex-col ${
                    plan.popular
                      ? "border-2 border-zinc-900 shadow-lg shadow-zinc-900/10 dark:border-white"
                      : "border-zinc-200 dark:border-zinc-800"
                  }`}
                >
                  {plan.popular && (
                    <div className="absolute -top-3 left-6">
                      <Badge>Most Popular</Badge>
                    </div>
                  )}
                  <CardHeader className="pb-4">
                    <CardTitle className="text-2xl">{plan.name}</CardTitle>
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      {plan.summary}
                    </p>
                    <div className="pt-2">
                      <span className="text-4xl font-bold">${price}</span>
                      <span className="text-zinc-500">
                        {billingLabel[billingMode].suffix}
                      </span>
                    </div>
                    <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                      {plan.capacity}
                    </p>
                  </CardHeader>
                  <CardContent className="flex flex-1 flex-col">
                    <ul className="mb-6 space-y-3">
                      {plan.features.map((feature) => (
                        <li
                          key={feature}
                          className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300"
                        >
                          <span className="mt-0.5 text-emerald-600">✓</span>
                          <span>{feature}</span>
                        </li>
                      ))}
                    </ul>
                    <div className="mt-auto space-y-3">
                      <Link href="/session/new" className="block">
                        <Button
                          className="w-full"
                          variant={plan.popular ? "default" : "outline"}
                        >
                          {plan.cta}
                        </Button>
                      </Link>
                      {plan.name === "Power" && (
                        <p className="text-xs leading-5 text-zinc-500 dark:text-zinc-400">
                          Best fit if you expect login gates, CAPTCHA, or want
                          browser takeover as part of normal usage.
                        </p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          <Card className="mt-8 border-dashed border-zinc-300 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900/60">
            <CardContent className="flex flex-col gap-4 py-6 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Concierge
                </p>
                <h3 className="mt-1 text-xl font-semibold">
                  Need human service on top of the product?
                </h3>
                <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
                  Dedicated hands-on application service, custom outreach, and
                  manual support should be priced separately from the self-serve
                  product.
                </p>
              </div>
              <Button variant="outline">Contact Sales</Button>
            </CardContent>
          </Card>
        </div>
      </section>

      <footer className="border-t border-zinc-200 px-6 py-8 dark:border-zinc-800">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 md:flex-row">
          <p className="text-sm text-zinc-500">
            © {new Date().getFullYear()} V2 Software LLC. All rights reserved.
          </p>
          <div className="flex gap-6 text-sm text-zinc-500">
            <a href="#" className="hover:text-zinc-900 dark:hover:text-white">
              Terms
            </a>
            <a href="#" className="hover:text-zinc-900 dark:hover:text-white">
              Privacy
            </a>
            <a href="#" className="hover:text-zinc-900 dark:hover:text-white">
              Contact
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
