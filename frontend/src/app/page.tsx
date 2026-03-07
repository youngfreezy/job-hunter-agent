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
    summary: "Try the workflow first and make sure it fits your search.",
    features: [
      "Guided setup and live job tracking",
      "One coached resume pass",
      "Review the shortlist before anything is sent",
      "Manual apply log with job links and saved materials",
    ],
    cta: "Start Free",
    popular: false,
  },
  {
    name: "Pro",
    monthlyPrice: 49,
    weeklyPrice: 19,
    capacity: "40 applications per week",
    summary: "For most people who want steady progress without losing control.",
    features: [
      "Resume coaching, tailored resumes, and cover letters",
      "Live updates and shortlist review",
      "Chat to adjust the search while it is running",
      "Manual apply log with saved resume and letter versions",
    ],
    cta: "Choose Pro",
    popular: true,
  },
  {
    name: "Power",
    monthlyPrice: 99,
    weeklyPrice: 39,
    capacity: "100 applications per week",
    summary: "For people who want hands-on control when job sites get messy.",
    features: [
      "Everything in Pro",
      "Live browser view during applications",
      "Take over the browser for sign-ins, verification prompts, and strange forms",
      "Priority help for blocked runs",
    ],
    cta: "Choose Power",
    popular: false,
  },
];

const steps = [
  {
    num: "1",
    title: "Tell it what you want",
    desc: "Add the roles, locations, salary floor, and remote preferences that actually matter to you.",
  },
  {
    num: "2",
    title: "Review the resume rewrite",
    desc: "The coach improves your resume, suggests a cover-letter angle, and pauses so you can approve or revise it.",
  },
  {
    num: "3",
    title: "Pick from a ranked shortlist",
    desc: "The app gathers matching roles, ranks them, and waits for your approval before it starts applying.",
  },
  {
    num: "4",
    title: "Stay in control while it applies",
    desc: "You can steer the session in chat, pause it, or take over the browser when a site needs a human touch.",
  },
  {
    num: "5",
    title: "See what happened for every job",
    desc: "Each submitted, skipped, or failed application is saved with the job link, tailored resume, and cover letter used.",
  },
  {
    num: "6",
    title: "Pick back up without starting over",
    desc: "If something blocks the run, you can resume from checkpoints instead of rebuilding the session from scratch.",
  },
];

const differentiators = [
  {
    title: "A human is still in charge",
    body: "You can steer the run in chat, pause it, or take over the browser when a site needs a real person.",
  },
  {
    title: "Quality checks before volume",
    body: "The app stops for resume review and shortlist approval before it sends applications at scale.",
  },
  {
    title: "A clear record of every attempt",
    body: "You can see what was sent, what was skipped, and what needs follow-up without piecing it together later.",
  },
];

const heroStats = [
  {
    value: "2 review points",
    label: "You approve the resume work and the job list before applications go out.",
  },
  {
    value: "Live control",
    label: "You can pause, chat, or take over the browser the moment a site needs you.",
  },
  {
    value: "Saved materials",
    label: "Every job keeps the version of the resume and letter that were used.",
  },
];

export default function Home() {
  const [billingMode, setBillingMode] = useState<BillingMode>("monthly");

  const billingLabel = useMemo(
    () => ({
      monthly: {
        suffix: "/month",
        helper: "Best value for an active search. Monthly is selected by default.",
      },
      weekly: {
        suffix: "/week",
        helper: "Choose weekly billing if you only need a short sprint.",
      },
    }),
    []
  );

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950 dark:bg-zinc-950 dark:text-white">
      <nav className="border-b border-zinc-200/80 bg-white/80 px-6 py-4 backdrop-blur-md dark:border-zinc-800 dark:bg-zinc-950/80">
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
        <div className="mx-auto max-w-7xl">
          <div className="relative overflow-hidden rounded-[36px] border border-zinc-200/80 bg-white px-8 py-10 shadow-[0_24px_80px_-36px_rgba(15,23,42,0.35)] dark:border-zinc-800 dark:bg-zinc-950 lg:px-12 lg:py-12">
            <div className="absolute -left-24 top-10 h-64 w-64 rounded-full bg-blue-200/40 blur-3xl dark:bg-blue-500/10" />
            <div className="absolute right-0 top-0 h-80 w-80 rounded-full bg-emerald-200/35 blur-3xl dark:bg-emerald-500/10" />
            <div className="relative grid gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-stretch">
              <div className="flex flex-col justify-between">
                <div>
                  <div className="mb-5 flex flex-wrap gap-2">
              <Badge variant="secondary" className="bg-blue-50 text-blue-700">
                Review before applications are sent
              </Badge>
              {/* <Badge
                variant="secondary"
                className="bg-emerald-50 text-emerald-700"
              >
                Take over when a site needs you
              </Badge> */}
                  </div>
                  <h1 className="max-w-4xl text-5xl font-bold tracking-tight text-zinc-950 dark:text-white md:text-6xl">
                    Job searching should feel less chaotic.
                    <br />
                    Keep your standards while the work gets done.
                  </h1>
                  <p className="mt-6 max-w-2xl text-lg leading-8 text-zinc-600 dark:text-zinc-400">
                    JobHunter Agent helps you search, improve your resume, review the
                    best matches, and send applications without giving up control.
                    When a job site needs a decision, you can step in right away
                    instead of losing momentum.
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
                </div>

                <div className="mt-8 grid gap-3 sm:grid-cols-3">
                  {heroStats.map((item) => (
                    <Card
                      key={item.value}
                      className="rounded-3xl border-zinc-200/80 bg-white/80 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80"
                    >
                      <CardContent className="p-5">
                        <p className="text-sm font-semibold text-zinc-900 dark:text-white">
                          {item.value}
                        </p>
                        <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
                          {item.label}
                        </p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>

              <div className="grid gap-4">
                <Card className="rounded-[32px] border-zinc-900 bg-zinc-950 text-white shadow-2xl shadow-zinc-900/20 dark:border-zinc-800">
                  <CardHeader className="pb-4">
                    <Badge className="w-fit bg-white/10 text-white hover:bg-white/10">
                      What your session feels like
                    </Badge>
                    <CardTitle className="text-2xl">
                      Calm automation with clear checkpoints
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4 text-sm text-zinc-300">
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-zinc-400">
                        First
                      </p>
                      <p className="mt-2 font-medium text-white">
                        You approve the resume work before anything scales
                      </p>
                      <p className="mt-1 leading-6">
                        The run pauses after the resume rewrite so you can adjust the direction early.
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-zinc-400">
                        Then
                      </p>
                      <p className="mt-2 font-medium text-white">
                        You approve the jobs before applications go out
                      </p>
                      <p className="mt-1 leading-6">
                        The shortlist is ranked for you, but the final call stays with you.
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-zinc-400">
                        Finally
                      </p>
                      <p className="mt-2 font-medium text-white">
                        You step in only when a site really needs you
                      </p>
                      <p className="mt-1 leading-6">
                        Chat, pause, and browser control are there for the moments automation should not guess.
                      </p>
                    </div>
                  </CardContent>
                </Card>
                <div className="grid gap-4 sm:grid-cols-3">
                  {differentiators.map((item) => (
                    <Card
                      key={item.title}
                      className="rounded-3xl border-zinc-200/80 bg-white/90 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80"
                    >
                      <CardContent className="p-5">
                        <p className="text-sm font-semibold text-zinc-900 dark:text-white">
                          {item.title}
                        </p>
                        <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
                          {item.body}
                        </p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mb-12 flex items-end justify-between gap-6">
            <div>
              <h2 className="text-3xl font-bold">How It Works</h2>
              <p className="mt-2 max-w-2xl text-zinc-600 dark:text-zinc-400">
                The workflow is built to save time without taking the important decisions away from you.
              </p>
            </div>
            <div className="hidden rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-600 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400 md:block">
              Six phases, two review stops, and live control when a site needs a person.
            </div>
          </div>
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
            {steps.map((step) => (
              <Card
                key={step.num}
                className="rounded-3xl border-zinc-200/80 bg-white/90 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
              >
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
                Start with the free plan, then move up when you want more applications and more hands-on control.
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
                  className={`relative flex h-full flex-col rounded-[32px] bg-white/95 shadow-[0_18px_48px_-32px_rgba(15,23,42,0.28)] ${
                    plan.popular
                      ? "border-2 border-zinc-900 dark:border-white"
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
                          browser takeover as part of regular usage.
                        </p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          <Card className="mt-8 rounded-[28px] border-dashed border-zinc-300 bg-white/90 shadow-sm dark:border-zinc-700 dark:bg-zinc-900/60">
            <CardContent className="flex flex-col gap-4 py-6 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Concierge
                </p>
                <h3 className="mt-1 text-xl font-semibold">
                  Need human service on top of the product?
                </h3>
                <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
                  If you want dedicated hands-on help, custom outreach, or a managed application service, that should be priced separately from the product itself.
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
