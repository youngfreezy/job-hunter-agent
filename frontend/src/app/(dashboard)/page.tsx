// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

// Note: page-level metadata must come from a separate metadata export in a
// server component.  Since this page is "use client", the root layout metadata
// covers it.  The JSON-LD structured data below provides additional SEO value.

const steps = [
  {
    num: "1",
    title: "Define your search criteria",
    desc: "Set target roles, locations, salary requirements, and remote work preferences.",
  },
  {
    num: "2",
    title: "Approve your optimized resume",
    desc: "Your AI enhances your resume to increase recruiter response rates, then pauses for your review.",
  },
  {
    num: "3",
    title: "Choose from your curated job matches",
    desc: "Your AI ranks the best opportunities across major job boards. You select which roles get your application.",
  },
  {
    num: "4",
    title: "Watch applications go out automatically",
    desc: "Your AI submits standard applications while you focus on what matters. For complex sites, your customized materials are ready so you finish in one click.",
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
    summary: "Best for focused job searches.",
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
    summary: "Maximum coverage for serious searchers.",
    features: [
      "50 application credits",
      "Everything in 10 Credits pack",
      "Priority application processing",
      "Direct browser control for complex sites",
      "Best value for most job seekers",
    ],
    cta: "Get 50 Credits",
    popular: true,
  },
];

const faqs = [
  {
    q: "How does JobHunter Agent apply to jobs?",
    a: "Our AI agent uses browser automation to fill out application forms on your behalf, using your approved resume and cover letter. You review and approve everything before submission. For sites that require human verification (CAPTCHAs, 2FA), your tailored materials are ready so you can complete them in seconds.",
  },
  {
    q: "Is my personal data safe?",
    a: "Your resume and personal information are encrypted at rest and in transit. We never share your data with third parties. All payment processing is handled by Stripe, a PCI-compliant payment processor. You can delete your data at any time.",
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
    a: "Partial attempts — where your resume was tailored, a cover letter was written, or a form was partially filled — use only 0.5 credits. You keep all the tailored materials and can apply manually. If a job was skipped entirely (duplicate, already applied), no credits are used.",
  },
  {
    q: "Can I get a refund?",
    a: "Partial attempts are charged at a reduced rate (0.5 credits) because real work was performed — your resume was tailored and a custom cover letter was generated. For unused credits, contact us within 30 days for a full refund.",
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
    {
      "@type": "Offer",
      price: "24.99",
      priceCurrency: "USD",
      description: "10 credit pack",
    },
    {
      "@type": "Offer",
      price: "99.99",
      priceCurrency: "USD",
      description: "50 credit pack",
    },
  ],
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

export default function Home() {
  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950 dark:bg-zinc-950 dark:text-white">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      {/* Nav */}
      <nav className="border-b border-zinc-200/80 bg-white/80 px-6 py-4 backdrop-blur-md dark:border-zinc-800 dark:bg-zinc-950/80">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <span className="text-xl font-bold tracking-tight">JobHunter Agent</span>
          <div className="flex items-center gap-4">
            <a
              href="#how-it-works"
              className="text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              How It Works
            </a>
            <a
              href="#pricing"
              className="text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              Pricing
            </a>
            <a
              href="#faq"
              className="text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              FAQ
            </a>
            <Link href="/session/new">
              <Button size="sm" data-umami-event="cta-get-started" data-umami-event-location="nav">
                Get Started Free
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
                <Link href="/session/new">
                  <Button
                    size="lg"
                    data-umami-event="cta-get-started"
                    data-umami-event-location="hero"
                  >
                    Start with 3 Free Applications
                  </Button>
                </Link>
              </div>
              <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
                No credit card required. Set up in under 5 minutes.
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
      <section id="how-it-works" className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mb-12">
            <h2 className="text-3xl font-bold">How It Works</h2>
            <p className="mt-2 max-w-2xl text-zinc-600 dark:text-zinc-400">
              Four steps from setup to submitted applications. You control every stage.
            </p>
          </div>
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
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
                  <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400">{step.desc}</p>
                </CardContent>
              </Card>
            ))}
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

      {/* Pricing */}
      <section id="pricing" className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mb-10">
            <h2 className="text-3xl font-bold">Pay Per Application. No Subscriptions.</h2>
            <p className="mt-2 max-w-2xl text-zinc-600 dark:text-zinc-400">
              Start with 3 free credits. Buy packs when you&apos;re ready. Successful applications
              cost 1 credit, partial attempts just 0.5.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-3">
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
                  <div className="pt-2">
                    <span className="text-4xl font-bold">{plan.priceLabel}</span>
                    {plan.price > 0 && (
                      <span className="ml-2 text-sm text-zinc-500">{plan.perApp}/application</span>
                    )}
                  </div>
                  <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {plan.apps} {plan.apps === 3 ? "free applications" : "credits"}
                  </p>
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
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <p className="mt-6 text-center text-sm text-zinc-500 dark:text-zinc-400">
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

      {/* FAQ */}
      <section id="faq" className="px-6 py-20">
        <div className="mx-auto max-w-3xl">
          <h2 className="mb-10 text-3xl font-bold">Frequently Asked Questions</h2>
          <div className="space-y-6">
            {faqs.map((faq) => (
              <div
                key={faq.q}
                className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950"
              >
                <h3 className="font-semibold text-zinc-900 dark:text-white">{faq.q}</h3>
                <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="px-6 pb-20">
        <div className="mx-auto max-w-4xl">
          <Card className="rounded-[28px] border-emerald-200 bg-gradient-to-r from-emerald-50 to-blue-50 shadow-sm dark:border-emerald-900 dark:from-emerald-950/30 dark:to-blue-950/30">
            <CardContent className="py-10 text-center">
              <h3 className="text-2xl font-bold">Ready to automate your job search?</h3>
              <p className="mx-auto mt-3 max-w-xl text-sm text-zinc-600 dark:text-zinc-400">
                Start with 3 free applications. No credit card required. See your tailored resume
                and matched jobs in under 5 minutes.
              </p>
              <div className="mt-6">
                <Link href="/session/new">
                  <Button
                    size="lg"
                    data-umami-event="cta-get-started"
                    data-umami-event-location="bottom"
                  >
                    Start Free
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
