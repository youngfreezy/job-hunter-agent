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
    summary: "See how it works before you commit.",
    features: [
      "AI-powered job search across top boards",
      "One resume coaching pass",
      "Review your shortlist before anything is sent",
      "Application log with saved resumes and cover letters",
    ],
    cta: "Start Free",
    popular: false,
  },
  {
    name: "Pro",
    monthlyPrice: 49,
    weeklyPrice: 19,
    capacity: "40 applications per week",
    summary: "For active job seekers who want steady momentum.",
    features: [
      "Resume coaching, tailored resumes, and cover letters",
      "Live progress updates and shortlist review",
      "Chat to adjust your search while it runs",
      "Application log with every version saved",
    ],
    cta: "Choose Pro",
    popular: true,
  },
  {
    name: "Power",
    monthlyPrice: 99,
    weeklyPrice: 39,
    capacity: "100 applications per week",
    summary: "Maximum coverage with hands-on control when you need it.",
    features: [
      "Everything in Pro",
      "Watch applications happen in real time",
      "Step in for logins, CAPTCHAs, and tricky forms",
      "Priority support for stuck applications",
    ],
    cta: "Choose Power",
    popular: false,
  },
];

const steps = [
  {
    num: "1",
    title: "Set your preferences",
    desc: "Tell us the roles, locations, salary range, and remote preferences that matter to you.",
  },
  {
    num: "2",
    title: "Get a resume upgrade",
    desc: "Our AI coach rewrites your resume for maximum impact, then pauses so you can review and approve it.",
  },
  {
    num: "3",
    title: "Review your shortlist",
    desc: "We find and rank matching jobs across top boards. You decide which ones to pursue.",
  },
  {
    num: "4",
    title: "We apply, you stay in control",
    desc: "Applications go out automatically. You can chat, pause, or step in anytime a site needs a human.",
  },
  {
    num: "5",
    title: "Track every application",
    desc: "Every submission is logged with the job link, tailored resume, and cover letter used. Nothing gets lost.",
  },
  {
    num: "6",
    title: "Pick up where you left off",
    desc: "Resume from any checkpoint. No need to start over if something gets interrupted.",
  },
];

const differentiators = [
  {
    title: "You stay in the driver's seat",
    body: "Chat with the agent, pause anytime, or take over the browser when a site needs a real person.",
  },
  {
    title: "Quality before quantity",
    body: "Your resume and shortlist are reviewed and approved before a single application goes out.",
  },
  {
    title: "Your complete job search command center",
    body: "Track every application, download tailored resumes, and follow up on skipped or failed attempts from one dashboard.",
  },
];

const heroStats = [
  {
    value: "2 checkpoints",
    label: "You approve your resume and shortlist before any applications go out.",
  },
  {
    value: "Real-time control",
    label: "Pause, chat, or take over the browser the moment you need to.",
  },
  {
    value: "Everything saved",
    label: "Every resume version, cover letter, and application result in one place.",
  },
];

export default function Home() {
  const [billingMode, setBillingMode] = useState<BillingMode>("monthly");

  const billingLabel = useMemo(
    () => ({
      monthly: {
        suffix: "/month",
        helper: "Best value for an active search.",
      },
      weekly: {
        suffix: "/week",
        helper: "Pay by the week if you only need a short sprint.",
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
            <Link
              href="/apply"
              className="text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              Review & Apply
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
                      You review everything before it&apos;s sent
                    </Badge>
                  </div>
                  <h1 className="max-w-4xl text-5xl font-bold tracking-tight text-zinc-950 dark:text-white md:text-6xl">
                    Your job search,
                    <br />
                    organized and on autopilot.
                  </h1>
                  <p className="mt-6 max-w-2xl text-lg leading-8 text-zinc-600 dark:text-zinc-400">
                    JobHunter Agent finds the right roles, tailors your resume,
                    and applies on your behalf. When it can, it handles
                    everything automatically. When a site requires human
                    interaction, your materials are ready so you can apply in
                    seconds.
                  </p>
                  <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 dark:border-amber-800 dark:bg-amber-950/30">
                    <p className="text-sm text-amber-800 dark:text-amber-300">
                      <span className="font-semibold">Good to know:</span> Not
                      every job site plays nicely with automation. Some require
                      logins, CAPTCHAs, or custom forms that only a human can
                      handle. When that happens, we save your tailored resume and
                      cover letter so you can finish the application yourself in
                      one click. Either way, you get a complete dashboard to
                      track every opportunity.
                    </p>
                  </div>
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
                      How a session works
                    </Badge>
                    <CardTitle className="text-2xl">
                      Smart automation with human checkpoints
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4 text-sm text-zinc-300">
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-zinc-400">
                        First
                      </p>
                      <p className="mt-2 font-medium text-white">
                        Your resume gets an expert-level rewrite
                      </p>
                      <p className="mt-1 leading-6">
                        The AI coach scores and improves your resume, then pauses so you can approve or tweak it.
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-zinc-400">
                        Then
                      </p>
                      <p className="mt-2 font-medium text-white">
                        You pick which jobs to go after
                      </p>
                      <p className="mt-1 leading-6">
                        We rank and shortlist matches. You choose which ones get your application.
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-zinc-400">
                        Finally
                      </p>
                      <p className="mt-2 font-medium text-white">
                        Applications go out, and you can step in anytime
                      </p>
                      <p className="mt-1 leading-6">
                        Automation handles what it can. For sites that need a human, your materials are saved and ready.
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

      {/* Review & Apply CTA Section */}
      <section className="px-6 pb-10">
        <div className="mx-auto max-w-6xl">
          <Card className="rounded-[28px] border-emerald-200 bg-gradient-to-r from-emerald-50 to-blue-50 shadow-sm dark:border-emerald-900 dark:from-emerald-950/30 dark:to-blue-950/30">
            <CardContent className="flex flex-col gap-4 py-8 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h3 className="text-xl font-semibold">
                  Review & Apply: Your Application Command Center
                </h3>
                <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
                  See every application across all your sessions in one place.
                  Download tailored resumes and cover letters, finish
                  applications that need a human touch, and track your
                  progress.
                </p>
              </div>
              <Link href="/apply">
                <Button size="lg" className="whitespace-nowrap">
                  Open Review & Apply
                </Button>
              </Link>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mb-12 flex items-end justify-between gap-6">
            <div>
              <h2 className="text-3xl font-bold">How It Works</h2>
              <p className="mt-2 max-w-2xl text-zinc-600 dark:text-zinc-400">
                Six simple steps from setup to applications sent. You stay in control at every stage.
              </p>
            </div>
            <div className="hidden rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-600 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400 md:block">
              Two approval stops. Full visibility. Zero guesswork.
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
                Start Free. Scale When You&apos;re Ready.
              </h2>
              <p className="mt-2 max-w-2xl text-zinc-600 dark:text-zinc-400">
                Try everything with the free plan. Upgrade when you want more applications and more control.
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
                          Best for sites that require logins, CAPTCHAs, or
                          custom portals where you want live browser control.
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
                  Want a hands-on service on top of the product?
                </h3>
                <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
                  For dedicated help, custom outreach strategies, or a fully managed application service, our concierge team has you covered.
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
