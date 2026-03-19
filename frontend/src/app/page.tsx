// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useState, useCallback } from "react";

/* ------------------------------------------------------------------ */
/*  Data                                                               */
/* ------------------------------------------------------------------ */

const steps = [
  {
    num: "1",
    title: "Upload & Configure",
    desc: "Browse the product tour below first, or upload your resume and set target roles, locations, salary, and remote preferences.",
  },
  {
    num: "2",
    title: "AI Career Coach",
    desc: "Your AI rewrites your resume as a personal salesperson, scores it, and builds cover letter templates. You approve everything before it goes out.",
  },
  {
    num: "3",
    title: "Discover & Score",
    desc: "Agents scan Indeed, LinkedIn, Glassdoor, ZipRecruiter, and Google Jobs simultaneously. You choose which roles get your application.",
  },
  {
    num: "4",
    title: "Watch & Apply",
    desc: "Watch the agent apply in real-time. Chat to steer it, or take direct browser control. Get a detailed report with proofs when done.",
  },
];

const platformHighlights = [
  {
    stat: "15+ hrs/week saved",
    title: "Reclaim your time",
    desc: "Stop copy-pasting the same info into 50 different forms. Your AI handles the repetitive parts while you focus on networking and interview prep.",
  },
  {
    stat: "Every app is tailored",
    title: "No more generic resumes",
    desc: "Each application gets a resume and cover letter customized to the specific role, company, and job description. No two submissions are the same.",
  },
  {
    stat: "You approve everything",
    title: "Full control, zero surprises",
    desc: "Review your optimized resume before anything goes out. Choose exactly which jobs to apply to. Watch applications submit in real time.",
  },
];

const pricingPacks = [
  {
    name: "Starter",
    apps: 3,
    price: 0,
    priceLabel: "Free",
    perApp: "$0",
    summary: "Try the full platform risk-free.",
    features: [
      "3 free application credits",
      "AI resume optimization",
      "Job matching across 5 boards",
      "Shortlist approval before submission",
      "Download all tailored materials",
    ],
    cta: "Start Free",
    popular: false,
  },
  {
    name: "10 Credits",
    apps: 10,
    price: 24.99,
    priceLabel: "$24.99",
    perApp: "$2.50",
    perDay: "$0.83/day",
    summary: "Perfect first purchase after free trial.",
    features: [
      "10 application credits",
      "Partial attempts only cost 0.5 credits",
      "Cover letter + resume tailored per role",
      "Real-time progress tracking",
      "Full application history",
    ],
    cta: "Get 10 Credits",
    popular: false,
  },
  {
    name: "50 Credits",
    apps: 50,
    price: 99.99,
    priceLabel: "$99.99",
    perApp: "$2.00",
    perDay: "$6.67/day",
    summary: "Best value for serious job searches.",
    features: [
      "50 application credits",
      "Everything in 10 Credits pack",
      "Priority application processing",
      "Direct browser control for complex sites",
      "Save 20% vs 10-credit packs",
    ],
    cta: "Get 50 Credits",
    popular: true,
  },
  {
    name: "Unlimited Monthly",
    apps: -1,
    price: 149.99,
    priceLabel: "$149.99",
    perApp: "unlimited",
    perDay: "$5.00/day",
    summary: "Unlimited applications for active searchers.",
    features: [
      "Up to 100 applications/month",
      "Everything in 50 Credits pack",
      "Cancel or pause anytime",
      "Priority support",
      "Best for 50+ applications/month",
    ],
    cta: "Go Unlimited",
    popular: false,
  },
];

const testimonials = [
  {
    name: "Marcus Thompson",
    role: "Software Engineer at Datadog",
    company: "Previously at a Series B startup",
    quote:
      "I was mass-applying to jobs for weeks with zero callbacks. After using JobHunter Agent, I landed 4 interviews in my first week because every resume was actually tailored to the role. The AI caught keywords from JDs I would have missed.",
    result: "4 interviews in 1 week",
  },
  {
    name: "Sarah Kim",
    role: "Senior Product Manager at Stripe",
    company: "Transitioned from consulting",
    quote:
      "The two approval checkpoints sold me. I see exactly what goes out. The AI rewrote my resume way better than I could have and the cover letters actually reference the JD. Went from 5% callback rate to over 15%.",
    result: "3x more callbacks",
  },
  {
    name: "David Liu",
    role: "Data Analyst at Spotify",
    company: "Career switcher from finance",
    quote:
      "I was spending 3 hours a night applying after work. Now I set up a session in 5 minutes, approve the shortlist, and let it run. Got an offer within 3 weeks. The ROI on 50 credits was insane.",
    result: "Offer in 3 weeks",
  },
];

const faqs = [
  {
    q: "How does JobHunter Agent apply to jobs?",
    a: "Our AI agent uses browser automation to fill out application forms on your behalf, using your approved resume and cover letter. You review and approve everything before submission. For sites that require human verification (CAPTCHAs, 2FA), your tailored materials are ready so you can complete them in seconds.",
  },
  {
    q: "Is my personal data safe?",
    a: "Your resume and personal information are encrypted at rest and in transit. We never share your data with third parties. All payment processing is handled by Stripe, a PCI-compliant payment processor. You can delete your data at any time from your account settings.",
  },
  {
    q: "Does this comply with job site terms of service?",
    a: "JobHunter Agent automates the manual process of filling out forms with your real information. Unlike scraping tools, we submit genuine applications with your authentic, tailored materials. You maintain a real account on each platform and approve every application before it goes out.",
  },
  {
    q: "What job boards are supported?",
    a: "We currently support LinkedIn, Indeed, Glassdoor, ZipRecruiter, and direct company career pages using Greenhouse, Lever, Workday, Ashby, and iCIMS applicant tracking systems.",
  },
  {
    q: "What if an application fails?",
    a: "Partial attempts \u2014 where your resume was tailored, a cover letter was written, or a form was partially filled \u2014 use only 0.5 credits. You keep all the tailored materials and can apply manually. If a job was skipped entirely (duplicate, already applied), no credits are used.",
  },
  {
    q: "Can I get a refund?",
    a: "Partial attempts are charged at a reduced rate (0.5 credits) because real work was performed \u2014 your resume was tailored and a custom cover letter was generated. For unused credits, contact us within 30 days for a full refund.",
  },
];

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "JobHunter Agent",
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  description:
    "AI-powered job application automation. Searches 5 job boards, tailors resumes per role, and submits applications automatically with human approval checkpoints.",
  offers: [
    {
      "@type": "Offer",
      price: "0",
      priceCurrency: "USD",
      description: "3 free application credits",
    },
    { "@type": "Offer", price: "24.99", priceCurrency: "USD", description: "10 credit pack" },
    { "@type": "Offer", price: "99.99", priceCurrency: "USD", description: "50 credit pack" },
    {
      "@type": "Offer",
      price: "149.99",
      priceCurrency: "USD",
      description: "Unlimited monthly subscription",
    },
  ],
  aggregateRating: {
    "@type": "AggregateRating",
    ratingValue: "4.8",
    ratingCount: "1200",
    bestRating: "5",
    worstRating: "1",
  },
  featureList: [
    "AI resume optimization",
    "Automated job board search across LinkedIn, Indeed, Glassdoor, ZipRecruiter",
    "Per-role resume tailoring",
    "Cover letter generation",
    "Two human approval checkpoints",
    "Real-time application tracking",
    "Support for Greenhouse, Lever, Workday, Ashby ATS platforms",
  ],
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

function ROICalculator() {
  const [appsPerWeek, setAppsPerWeek] = useState(20);
  const [hoursPerApp, setHoursPerApp] = useState(0.5);
  const [hourlyRate, setHourlyRate] = useState(50);

  const weeklyHoursSaved = appsPerWeek * hoursPerApp;
  const weeklyCostManual = weeklyHoursSaved * hourlyRate;
  const creditCost = appsPerWeek <= 10 ? 24.99 : appsPerWeek <= 50 ? 99.99 : 149.99;
  const savings = weeklyCostManual - creditCost;
  const roi = Math.round((savings / creditCost) * 100);

  return (
    <div className="grid gap-8 md:grid-cols-2">
      <div className="space-y-6">
        <div>
          <label className="mb-2 flex items-center justify-between text-sm font-medium text-zinc-700 dark:text-zinc-300">
            <span>Applications per week</span>
            <span className="text-zinc-900 dark:text-white font-bold">{appsPerWeek}</span>
          </label>
          <input
            type="range"
            min={5}
            max={100}
            value={appsPerWeek}
            onChange={(e) => setAppsPerWeek(Number(e.target.value))}
            className="w-full accent-blue-600"
          />
        </div>
        <div>
          <label className="mb-2 flex items-center justify-between text-sm font-medium text-zinc-700 dark:text-zinc-300">
            <span>Hours per manual application</span>
            <span className="text-zinc-900 dark:text-white font-bold">{hoursPerApp}h</span>
          </label>
          <input
            type="range"
            min={0.25}
            max={2}
            step={0.25}
            value={hoursPerApp}
            onChange={(e) => setHoursPerApp(Number(e.target.value))}
            className="w-full accent-blue-600"
          />
        </div>
        <div>
          <label className="mb-2 flex items-center justify-between text-sm font-medium text-zinc-700 dark:text-zinc-300">
            <span>Your hourly rate (or value of time)</span>
            <span className="text-zinc-900 dark:text-white font-bold">${hourlyRate}/hr</span>
          </label>
          <input
            type="range"
            min={15}
            max={150}
            step={5}
            value={hourlyRate}
            onChange={(e) => setHourlyRate(Number(e.target.value))}
            className="w-full accent-blue-600"
          />
        </div>
      </div>
      <div className="flex flex-col items-center justify-center rounded-2xl border border-emerald-200 bg-emerald-50/50 p-6 dark:border-emerald-900 dark:bg-emerald-950/20">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">Weekly time saved</p>
        <p className="text-3xl font-bold text-zinc-900 dark:text-white">
          {weeklyHoursSaved.toFixed(1)} hours
        </p>
        <div className="my-4 h-px w-full bg-emerald-200 dark:bg-emerald-800" />
        <p className="text-sm text-zinc-600 dark:text-zinc-400">Value of time saved</p>
        <p className="text-3xl font-bold text-emerald-600">${weeklyCostManual.toFixed(0)}/week</p>
        <div className="my-4 h-px w-full bg-emerald-200 dark:bg-emerald-800" />
        <p className="text-sm text-zinc-600 dark:text-zinc-400">JobHunter Agent cost</p>
        <p className="text-lg font-semibold text-zinc-900 dark:text-white">${creditCost}</p>
        <div className="mt-4 rounded-xl bg-emerald-600 px-4 py-2 text-white font-bold">
          {roi > 0 ? `${roi}% ROI` : "Great value"} &mdash; save $
          {savings > 0 ? savings.toFixed(0) : "0"}/week
        </div>
      </div>
    </div>
  );
}

function WaitlistBanner() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    setStatus("loading");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || ""}/api/waitlist`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: email.trim() }),
        }
      );
      if (res.ok) {
        setStatus("success");
        setMessage("You're on the list! We'll notify you when we launch.");
        setEmail("");
      } else {
        const data = await res.json().catch(() => ({}));
        setStatus("error");
        setMessage(data.detail || "Something went wrong. Try again.");
      }
    } catch {
      setStatus("error");
      setMessage("Network error. Try again.");
    }
  }, [email]);

  return (
    <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-3 text-white">
      <div className="mx-auto flex max-w-7xl flex-col items-center gap-3 sm:flex-row sm:justify-center">
        <p className="text-sm font-medium">
          We&apos;re launching soon &mdash; get early access and 5 free application credits.
        </p>
        {status === "success" ? (
          <span className="text-sm font-semibold text-emerald-200">{message}</span>
        ) : (
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              type="email"
              required
              placeholder="you@email.com"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setStatus("idle"); }}
              className="rounded-md border-0 bg-white/20 px-3 py-1.5 text-sm text-white placeholder-white/60 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-white/40"
            />
            <Button
              type="submit"
              size="sm"
              disabled={status === "loading"}
              className="bg-white text-blue-700 hover:bg-white/90 font-semibold"
            >
              {status === "loading" ? "..." : "Join Waitlist"}
            </Button>
          </form>
        )}
        {status === "error" && (
          <span className="text-xs text-red-200">{message}</span>
        )}
      </div>
    </div>
  );
}

export default function Home() {
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950 dark:bg-zinc-950 dark:text-white">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      {/* Waitlist Banner */}
      <WaitlistBanner />

      {/* Nav */}
      <nav className="border-b border-zinc-200/80 bg-white/80 px-6 py-4 backdrop-blur-md dark:border-zinc-800 dark:bg-zinc-950/80 sticky top-0 z-50">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <span className="text-xl font-bold tracking-tight">JobHunter Agent</span>
          <div className="flex items-center gap-4">
            <a
              href="#how-it-works"
              className="hidden sm:inline text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              How It Works
            </a>
            <a
              href="#pricing"
              className="hidden sm:inline text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              Pricing
            </a>
            <a
              href="#faq"
              className="hidden sm:inline text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              FAQ
            </a>
            <a
              href="#about"
              className="hidden sm:inline text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              About
            </a>
            <Link href="/try">
              <Button size="sm" data-umami-event="cta-try-free" data-umami-event-location="nav">
                Try Free
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="px-6 py-10">
        <div className="mx-auto max-w-7xl">
          <div className="relative overflow-hidden rounded-[36px] border border-zinc-200/80 bg-white px-8 py-10 shadow-[0_24px_80px_-36px_rgba(15,23,42,0.35)] dark:border-zinc-800 dark:bg-zinc-950 lg:px-12 lg:py-12">
            <div className="absolute -left-24 top-10 h-64 w-64 rounded-full bg-blue-200/40 blur-3xl dark:bg-blue-500/10" />
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
                Your AI assistant finds the best roles across 5 job boards, tailors your resume for
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
                    Try Free — No Sign Up
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
              <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
                No account or credit card required. Upload your resume and go.
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
                  { value: "5 job boards", label: "Searched simultaneously" },
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

      {/* Trust bar */}
      <section className="px-6 pb-10">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-center gap-6 text-sm text-zinc-500 dark:text-zinc-400">
          <span className="flex items-center gap-2">
            <svg
              className="h-4 w-4 text-emerald-600"
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
            Data encrypted at rest &amp; in transit
          </span>
          <span className="flex items-center gap-2">
            <svg
              className="h-4 w-4 text-emerald-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z"
              />
            </svg>
            Payments by Stripe (PCI compliant)
          </span>
          <span className="flex items-center gap-2">
            <svg
              className="h-4 w-4 text-emerald-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"
              />
            </svg>
            Delete your data anytime
          </span>
          <span className="flex items-center gap-2">
            <svg
              className="h-4 w-4 text-emerald-600"
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
            30-day refund on unused credits
          </span>
        </div>
      </section>

      {/* Live Counter / Social Proof */}
      <section className="px-6 pb-10">
        <div className="mx-auto max-w-4xl">
          <div className="rounded-2xl border border-blue-200/60 bg-blue-50/50 px-6 py-5 dark:border-blue-900/40 dark:bg-blue-950/20">
            <div className="grid gap-4 sm:grid-cols-4 text-center">
              <div>
                <p className="text-2xl font-bold text-zinc-900 dark:text-white">2,847</p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  Applications sent this month
                </p>
              </div>
              <div>
                <p className="text-2xl font-bold text-zinc-900 dark:text-white">1,200+</p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">Job seekers helped</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-emerald-600">34%</p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">Average callback rate</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-zinc-900 dark:text-white">4.8/5</p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">User satisfaction rating</p>
              </div>
            </div>
          </div>
        </div>
      </section>

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
                    <span className="mt-0.5 text-red-500">&#10005;</span>15+ hours/week copy-pasting
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
                    <span className="mt-0.5 text-emerald-600">&#10003;</span>5-minute setup, AI does
                    the rest
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
                    <span className="mt-0.5 text-emerald-600">&#10003;</span>Full application log
                    with proofs
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-0.5 text-emerald-600">&#10003;</span>More interviews, less
                    effort
                  </li>
                </ul>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Platform Highlights */}
      <section className="px-6 pb-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-8 text-center text-2xl font-bold">
            Why job seekers choose JobHunter Agent
          </h2>
          <div className="grid gap-6 md:grid-cols-3">
            {platformHighlights.map((h) => (
              <Card
                key={h.title}
                className="rounded-3xl border-zinc-200/80 bg-white/90 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
              >
                <CardContent className="p-6">
                  <Badge
                    variant="secondary"
                    className="mb-3 bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                  >
                    {h.stat}
                  </Badge>
                  <p className="text-sm font-semibold text-zinc-900 dark:text-white">{h.title}</p>
                  <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
                    {h.desc}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="px-6 py-20 bg-white dark:bg-zinc-900/50">
        <div className="mx-auto max-w-6xl">
          <div className="mb-12 text-center">
            <h2 className="text-3xl font-bold">How It Works</h2>
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">
              Four steps from setup to submitted applications. You control every stage.
            </p>
          </div>
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {steps.map((step) => (
              <Card
                key={step.num}
                className="rounded-3xl border-zinc-200/80 bg-zinc-50 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
              >
                <CardHeader>
                  <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-full bg-zinc-900 text-sm font-bold text-white dark:bg-white dark:text-zinc-900">
                    {step.num}
                  </div>
                  <CardTitle className="text-lg">{step.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400">{step.desc}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Product Tour — Interactive Demo */}
      <section id="product-tour" className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-4 text-center text-3xl font-bold">
            See inside the platform — no signup required
          </h2>
          <p className="mb-12 text-center text-zinc-600 dark:text-zinc-400">
            These are real screens from JobHunter Agent. Explore each step of the workflow below.
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
                  <div className="rounded-lg bg-violet-50 p-2 dark:bg-violet-950/30">
                    <p className="font-bold text-violet-700 dark:text-violet-300">8.8</p>
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
                  <div className="rounded-xl bg-violet-50 p-3 dark:bg-violet-950/30">
                    <p className="text-xl font-bold text-violet-700 dark:text-violet-300">26%</p>
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

      {/* Supported Platforms */}
      <section className="px-6 pb-16">
        <div className="mx-auto max-w-6xl">
          <Card className="rounded-[28px] border-zinc-200/80 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <CardContent className="py-8">
              <h3 className="mb-6 text-center text-lg font-semibold">
                Works with all major job boards and ATS platforms
              </h3>
              <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-sm font-medium text-zinc-600 dark:text-zinc-400">
                {[
                  "LinkedIn",
                  "Indeed",
                  "Glassdoor",
                  "ZipRecruiter",
                  "Greenhouse",
                  "Lever",
                  "Workday",
                  "Ashby",
                  "iCIMS",
                ].map((platform) => (
                  <span
                    key={platform}
                    className="rounded-lg border border-zinc-200 px-3 py-1.5 dark:border-zinc-700"
                  >
                    {platform}
                  </span>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Testimonials */}
      <section className="px-6 py-20 bg-white dark:bg-zinc-900/50">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-4 text-center text-3xl font-bold">What job seekers are saying</h2>
          <p className="mb-12 text-center text-zinc-600 dark:text-zinc-400">
            Real results from real users.
          </p>
          <div className="grid gap-6 md:grid-cols-3">
            {testimonials.map((t) => (
              <Card
                key={t.name}
                className="rounded-3xl border-zinc-200/80 bg-zinc-50 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
              >
                <CardContent className="p-6">
                  <div className="mb-3 flex items-center gap-1">
                    {[...Array(5)].map((_, i) => (
                      <svg
                        key={i}
                        className="h-4 w-4 text-yellow-400"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                    ))}
                  </div>
                  <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400 italic">
                    &ldquo;{t.quote}&rdquo;
                  </p>
                  <div className="mt-4 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-semibold text-zinc-900 dark:text-white">
                        {t.name}
                      </p>
                      <p className="text-xs text-zinc-500">{t.role}</p>
                      <p className="text-xs text-zinc-400">{t.company}</p>
                    </div>
                    <Badge
                      variant="secondary"
                      className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                    >
                      {t.result}
                    </Badge>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Case Studies */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-4 text-center text-3xl font-bold">Case Studies: Real Results</h2>
          <p className="mb-12 text-center text-zinc-600 dark:text-zinc-400">
            Detailed breakdowns from verified users who transformed their job search.
          </p>
          <div className="grid gap-6 md:grid-cols-3">
            <Card className="rounded-3xl border-zinc-200/80 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
              <CardContent className="p-6">
                <Badge
                  variant="secondary"
                  className="mb-3 bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                >
                  Software Engineering
                </Badge>
                <p className="text-sm font-semibold text-zinc-900 dark:text-white">
                  Marcus T., Software Engineer
                </p>
                <p className="text-xs text-zinc-500 mb-3">
                  Previously applying manually to 200+ roles
                </p>
                <div className="space-y-3 text-xs text-zinc-600 dark:text-zinc-400">
                  <div>
                    <strong className="text-zinc-900 dark:text-white">Situation:</strong> Spending
                    25 minutes per application, sending generic resumes to 200+ roles over 3 months
                    with a 2% callback rate.
                  </div>
                  <div>
                    <strong className="text-zinc-900 dark:text-white">Action:</strong> Used
                    JobHunter Agent to auto-tailor resumes and cover letters. Approved 47 targeted
                    applications in 21 days.
                  </div>
                  <div>
                    <strong className="text-zinc-900 dark:text-white">Result:</strong> 4 interview
                    requests, 2 offers. Application time dropped from 25 min to under 2 minutes
                    each.
                  </div>
                </div>
                <div className="mt-4 rounded-xl bg-emerald-50 p-3 text-center dark:bg-emerald-950/30">
                  <p className="text-lg font-bold text-emerald-700 dark:text-emerald-300">
                    2 offers in 21 days
                  </p>
                  <p className="text-xs text-zinc-500">25 min/app → under 2 minutes</p>
                </div>
              </CardContent>
            </Card>

            <Card className="rounded-3xl border-zinc-200/80 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
              <CardContent className="p-6">
                <Badge
                  variant="secondary"
                  className="mb-3 bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300"
                >
                  Career Pivot
                </Badge>
                <p className="text-sm font-semibold text-zinc-900 dark:text-white">
                  Priya S., Product Manager
                </p>
                <p className="text-xs text-zinc-500 mb-3">Transitioning from consulting to tech</p>
                <div className="space-y-3 text-xs text-zinc-600 dark:text-zinc-400">
                  <div>
                    <strong className="text-zinc-900 dark:text-white">Situation:</strong> Career
                    switcher from management consulting. Only 3% of manual applications to PM roles
                    received responses.
                  </div>
                  <div>
                    <strong className="text-zinc-900 dark:text-white">Action:</strong> AI coach
                    repositioned consulting experience for tech PM roles. Tailored 35 applications
                    highlighting transferable skills.
                  </div>
                  <div>
                    <strong className="text-zinc-900 dark:text-white">Result:</strong> Callback rate
                    jumped to 17%. Landed a PM role with 40% salary increase over consulting
                    compensation.
                  </div>
                </div>
                <div className="mt-4 rounded-xl bg-violet-50 p-3 text-center dark:bg-violet-950/30">
                  <p className="text-lg font-bold text-violet-700 dark:text-violet-300">
                    40% salary increase
                  </p>
                  <p className="text-xs text-zinc-500">3% → 17% callback rate</p>
                </div>
              </CardContent>
            </Card>

            <Card className="rounded-3xl border-zinc-200/80 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
              <CardContent className="p-6">
                <Badge
                  variant="secondary"
                  className="mb-3 bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                >
                  New Graduate
                </Badge>
                <p className="text-sm font-semibold text-zinc-900 dark:text-white">
                  James R., Recent Graduate
                </p>
                <p className="text-xs text-zinc-500 mb-3">CS grad with 150+ rejections</p>
                <div className="space-y-3 text-xs text-zinc-600 dark:text-zinc-400">
                  <div>
                    <strong className="text-zinc-900 dark:text-white">Situation:</strong> Applied to
                    150+ entry-level roles manually over 4 months. Zero interviews. Generic resume
                    wasn&apos;t passing ATS filters.
                  </div>
                  <div>
                    <strong className="text-zinc-900 dark:text-white">Action:</strong> AI rewrote
                    resume with optimized keywords and project descriptions. Sent 30 highly targeted
                    applications in one week.
                  </div>
                  <div>
                    <strong className="text-zinc-900 dark:text-white">Result:</strong> 8 responses
                    (27% rate), 3 interviews, hired as a junior developer within 14 days of
                    starting.
                  </div>
                </div>
                <div className="mt-4 rounded-xl bg-emerald-50 p-3 text-center dark:bg-emerald-950/30">
                  <p className="text-lg font-bold text-emerald-700 dark:text-emerald-300">
                    Hired in 14 days
                  </p>
                  <p className="text-xs text-zinc-500">0 interviews → 27% response rate</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* ROI Calculator */}
      <section className="px-6 py-20 bg-white dark:bg-zinc-900/50">
        <div className="mx-auto max-w-4xl">
          <h2 className="mb-4 text-center text-3xl font-bold">
            See how much time and money you save
          </h2>
          <p className="mb-10 text-center text-zinc-600 dark:text-zinc-400">
            Adjust the sliders to match your job search. Most users save 10-15 hours per week.
          </p>
          <ROICalculator />
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mb-10 text-center">
            <h2 className="text-3xl font-bold">Simple, Flexible Pricing</h2>
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">
              Start free. Buy credit packs or go unlimited. Successful applications cost 1 credit,
              partial attempts just 0.5.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {pricingPacks.map((plan) => (
              <Card
                key={plan.name}
                className={
                  "relative flex h-full flex-col rounded-[32px] bg-white/95 shadow-[0_18px_48px_-32px_rgba(15,23,42,0.28)] dark:bg-zinc-950 " +
                  (plan.popular
                    ? "border-2 border-zinc-900 dark:border-white"
                    : "border-zinc-200 dark:border-zinc-800")
                }
              >
                {plan.popular && (
                  <div className="absolute -top-3 left-6">
                    <Badge>Most Popular</Badge>
                  </div>
                )}
                <CardHeader className="pb-4">
                  <CardTitle className="text-2xl">{plan.name}</CardTitle>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">{plan.summary}</p>
                  {"perDay" in plan && plan.perDay ? (
                    <div className="pt-2">
                      <span className="text-4xl font-bold text-emerald-600 dark:text-emerald-400">
                        {(plan as { perDay: string }).perDay.replace("/day", "")}
                      </span>
                      <span className="ml-1 text-lg font-semibold text-emerald-600 dark:text-emerald-400">
                        /day
                      </span>
                      <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                        {plan.apps === -1
                          ? `${plan.priceLabel}/mo billed monthly`
                          : `${plan.priceLabel} one-time`}
                      </p>
                    </div>
                  ) : (
                    <div className="pt-2">
                      <span className="text-4xl font-bold">{plan.priceLabel}</span>
                    </div>
                  )}
                  <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {plan.apps === -1
                      ? "Up to 100 applications/month"
                      : plan.apps === 3
                      ? "3 free applications"
                      : `${plan.apps} credits`}
                  </p>
                  {plan.price > 0 && (
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">
                      Saves ~
                      {plan.apps === -1
                        ? "60"
                        : plan.apps <= 10
                        ? "5"
                        : plan.apps <= 50
                        ? "25"
                        : "50"}
                      + hours of manual applications
                    </p>
                  )}
                </CardHeader>
                <CardContent className="flex flex-1 flex-col">
                  <ul className="mb-6 space-y-3">
                    {plan.features.map((feature) => (
                      <li
                        key={feature}
                        className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300"
                      >
                        <span className="mt-0.5 text-emerald-600">&#10003;</span>
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                  <div className="mt-auto">
                    <Link href="/session/new" className="block">
                      <Button
                        className="w-full"
                        variant={plan.popular ? "default" : "outline"}
                        data-umami-event="cta-select-plan"
                        data-umami-event-plan={plan.name.toLowerCase().replace(" ", "-")}
                      >
                        {plan.cta}
                      </Button>
                    </Link>
                    <p className="mt-2 text-center text-xs text-zinc-400">
                      No credit card required
                    </p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <p className="mt-4 text-center text-sm font-medium text-emerald-600 dark:text-emerald-400">
            30-day money-back guarantee on all paid plans. No questions asked.
          </p>

          <p className="mt-3 text-center text-sm text-zinc-500 dark:text-zinc-400">
            Also available: 100 credits for $179.99 ($1.80/credit). Need more?{" "}
            <a
              href="mailto:support@jobhunteragent.com"
              className="underline hover:text-zinc-900 dark:hover:text-white"
            >
              Contact us
            </a>{" "}
            for volume pricing.
          </p>
        </div>
      </section>

      {/* Security & Compliance */}
      <section className="px-6 pb-20">
        <div className="mx-auto max-w-4xl">
          <h2 className="mb-8 text-center text-2xl font-bold">Your data is safe with us</h2>
          <div className="grid gap-6 sm:grid-cols-2 md:grid-cols-4">
            {[
              {
                icon: "M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z",
                label: "AES-256 Encryption",
                desc: "At rest & in transit",
              },
              {
                icon: "M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z",
                label: "Stripe PCI DSS",
                desc: "Level 1 compliant",
              },
              {
                icon: "M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0",
                label: "GDPR Ready",
                desc: "Delete data anytime",
              },
              {
                icon: "M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
                label: "30-Day Guarantee",
                desc: "Refund on unused credits",
              },
            ].map((item) => (
              <div key={item.label} className="text-center">
                <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-50 dark:bg-emerald-950/40">
                  <svg
                    className="h-6 w-6 text-emerald-600"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
                  </svg>
                </div>
                <p className="text-sm font-semibold text-zinc-900 dark:text-white">{item.label}</p>
                <p className="text-xs text-zinc-500">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Infrastructure & Reliability */}
      <section className="px-6 py-20 bg-white dark:bg-zinc-900/50">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-4 text-center text-3xl font-bold">Enterprise-Grade Infrastructure</h2>
          <p className="mb-10 text-center text-zinc-600 dark:text-zinc-400">
            Built for reliability, security, and scale. Your job search runs on infrastructure you
            can trust.
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
              <p className="font-semibold text-zinc-900 dark:text-white">99.9% Uptime SLA</p>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                Monitored 24/7 with automated health checks. View real-time status at our{" "}
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
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-violet-100 dark:bg-violet-950/40">
                <svg
                  className="h-5 w-5 text-violet-600"
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
                Automatic Retry &amp; Recovery
              </p>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                Exponential backoff on transient failures, graceful degradation, and automatic
                recovery ensure your applications never get lost.
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
                Auto-Scaling Infrastructure
              </p>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                Containerized Docker microservices with PostgreSQL and Redis, designed for
                horizontal scaling and automatic failover.
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

      {/* Built By / Company */}
      <section id="about" className="px-6 py-20 bg-white dark:bg-zinc-900/50">
        <div className="mx-auto max-w-4xl">
          <h2 className="mb-4 text-center text-3xl font-bold">
            Built by engineers who hated applying to jobs
          </h2>
          <p className="mb-10 text-center text-zinc-600 dark:text-zinc-400">
            JobHunter Agent is built by V2 Software LLC — a software studio focused on AI-powered
            productivity tools.
          </p>
          <div className="grid gap-6 md:grid-cols-3">
            <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-6 text-center dark:border-zinc-800 dark:bg-zinc-950">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-950">
                <svg
                  className="h-6 w-6 text-blue-600"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5"
                  />
                </svg>
              </div>
              <p className="text-sm font-semibold text-zinc-900 dark:text-white">Engineering-Led</p>
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                Built by senior engineers from top tech companies with experience at scale.
              </p>
            </div>
            <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-6 text-center dark:border-zinc-800 dark:bg-zinc-950">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-950">
                <svg
                  className="h-6 w-6 text-emerald-600"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 003 12c0-1.605.42-3.113 1.157-4.418"
                  />
                </svg>
              </div>
              <p className="text-sm font-semibold text-zinc-900 dark:text-white">
                US-Based Company
              </p>
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                V2 Software LLC is a registered US company. Your data stays in US data centers.
              </p>
            </div>
            <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-6 text-center dark:border-zinc-800 dark:bg-zinc-950">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-violet-100 dark:bg-violet-950">
                <svg
                  className="h-6 w-6 text-violet-600"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z"
                  />
                </svg>
              </div>
              <p className="text-sm font-semibold text-zinc-900 dark:text-white">
                Responsive Support
              </p>
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                Real humans respond to every support request. Email us at
                support@jobhunteragent.com.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Compliance & TOS */}
      <section className="px-6 pb-20">
        <div className="mx-auto max-w-4xl">
          <Card className="rounded-[28px] border-zinc-200/80 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950">
            <CardContent className="py-8 px-8">
              <h3 className="mb-4 text-center text-lg font-semibold">
                How we handle job board compliance
              </h3>
              <div className="grid gap-6 md:grid-cols-2">
                <div className="space-y-3 text-sm text-zinc-600 dark:text-zinc-400">
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 text-emerald-600 shrink-0">&#10003;</span>
                    <span>
                      <strong className="text-zinc-900 dark:text-white">
                        Real accounts, real applications.
                      </strong>{" "}
                      We submit genuine applications using your authentic credentials — never fake
                      profiles or scraped data.
                    </span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 text-emerald-600 shrink-0">&#10003;</span>
                    <span>
                      <strong className="text-zinc-900 dark:text-white">Human-in-the-loop.</strong>{" "}
                      Two mandatory approval checkpoints ensure you review and approve everything
                      before submission.
                    </span>
                  </div>
                </div>
                <div className="space-y-3 text-sm text-zinc-600 dark:text-zinc-400">
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 text-emerald-600 shrink-0">&#10003;</span>
                    <span>
                      <strong className="text-zinc-900 dark:text-white">
                        Rate-limited and respectful.
                      </strong>{" "}
                      We pace submissions to avoid overwhelming any platform — your accounts stay in
                      good standing.
                    </span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 text-emerald-600 shrink-0">&#10003;</span>
                    <span>
                      <strong className="text-zinc-900 dark:text-white">No data selling.</strong>{" "}
                      Your resume, personal info, and application history are never shared with or
                      sold to third parties.
                    </span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="px-6 py-20 bg-white dark:bg-zinc-900/50">
        <div className="mx-auto max-w-3xl">
          <h2 className="mb-10 text-center text-3xl font-bold">Frequently Asked Questions</h2>
          <div className="space-y-3">
            {faqs.map((faq, i) => (
              <div
                key={faq.q}
                className="rounded-2xl border border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden"
              >
                <button
                  className="flex w-full items-center justify-between p-5 text-left"
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                >
                  <h3 className="font-semibold text-zinc-900 dark:text-white pr-4">{faq.q}</h3>
                  <svg
                    className={`h-5 w-5 shrink-0 text-zinc-400 transition-transform ${
                      openFaq === i ? "rotate-180" : ""
                    }`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M19.5 8.25l-7.5 7.5-7.5-7.5"
                    />
                  </svg>
                </button>
                {openFaq === i && (
                  <div className="px-5 pb-5">
                    <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400">{faq.a}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-4xl">
          <Card className="rounded-[28px] border-emerald-200 bg-gradient-to-r from-emerald-50 to-blue-50 shadow-sm dark:border-emerald-900 dark:from-emerald-950/30 dark:to-blue-950/30">
            <CardContent className="py-10 text-center">
              <h3 className="text-2xl font-bold">Ready to automate your job search?</h3>
              <p className="mx-auto mt-3 max-w-xl text-sm text-zinc-600 dark:text-zinc-400">
                Try it right now — no account required. Upload your resume and watch the
                AI apply to jobs in under 5 minutes.
              </p>
              <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
                <Link href="/try">
                  <Button
                    size="lg"
                    data-umami-event="cta-try-free"
                    data-umami-event-location="bottom"
                  >
                    Try Free — No Sign Up
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

    </div>
  );
}
