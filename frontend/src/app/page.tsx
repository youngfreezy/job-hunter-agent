"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";

/* ------------------------------------------------------------------ */
/*  Data                                                               */
/* ------------------------------------------------------------------ */

const steps = [
  {
    num: "1",
    title: "Upload & Configure",
    desc: "Upload your resume, set target roles, locations, salary, and remote preferences.",
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
    name: "20 Credits",
    apps: 20,
    price: 29.99,
    priceLabel: "$29.99",
    perApp: "$1.50",
    summary: "Best for focused job searches.",
    features: [
      "20 application credits",
      "Partial attempts only cost 0.5 credits",
      "Cover letter + resume tailored per role",
      "Real-time progress tracking",
      "Full application history",
    ],
    cta: "Get 20 Credits",
    popular: false,
  },
  {
    name: "50 Credits",
    apps: 50,
    price: 64.99,
    priceLabel: "$64.99",
    perApp: "$1.30",
    summary: "Maximum coverage for serious searchers.",
    features: [
      "50 application credits",
      "Everything in 20 Credits pack",
      "Priority application processing",
      "Direct browser control for complex sites",
      "Best value for most job seekers",
    ],
    cta: "Get 50 Credits",
    popular: true,
  },
];

const testimonials = [
  {
    name: "Marcus T.",
    role: "Software Engineer",
    quote:
      "I was mass-applying to jobs for weeks with zero callbacks. After using JobHunter Agent, I landed 4 interviews in my first week because every resume was actually tailored to the role.",
    result: "4 interviews in 1 week",
  },
  {
    name: "Sarah K.",
    role: "Product Manager",
    quote:
      "The two approval checkpoints sold me. I see exactly what goes out. The AI rewrote my resume way better than I could have and the cover letters actually reference the JD.",
    result: "3x more callbacks",
  },
  {
    name: "David L.",
    role: "Data Analyst",
    quote:
      "I was spending 3 hours a night applying after work. Now I set up a session in 5 minutes, approve the shortlist, and let it run. Got an offer within 3 weeks.",
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
    { "@type": "Offer", price: "0", priceCurrency: "USD", description: "3 free application credits" },
    { "@type": "Offer", price: "29.99", priceCurrency: "USD", description: "20 credit pack" },
    { "@type": "Offer", price: "64.99", priceCurrency: "USD", description: "50 credit pack" },
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

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function Home() {
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950 dark:bg-zinc-950 dark:text-white">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      {/* Nav */}
      <nav className="border-b border-zinc-200/80 bg-white/80 px-6 py-4 backdrop-blur-md dark:border-zinc-800 dark:bg-zinc-950/80 sticky top-0 z-50">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <span className="text-xl font-bold tracking-tight">JobHunter Agent</span>
          <div className="flex items-center gap-4">
            <a href="#how-it-works" className="hidden sm:inline text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white">How It Works</a>
            <a href="#pricing" className="hidden sm:inline text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white">Pricing</a>
            <a href="#faq" className="hidden sm:inline text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white">FAQ</a>
            <Link href="/session/new">
              <Button size="sm" data-umami-event="cta-get-started" data-umami-event-location="nav">Start Free</Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-7xl">
          <div className="relative overflow-hidden rounded-[36px] border border-zinc-200/80 bg-white px-8 py-10 shadow-[0_24px_80px_-36px_rgba(15,23,42,0.35)] dark:border-zinc-800 dark:bg-zinc-950 lg:px-12 lg:py-12">
            <div className="absolute -left-24 top-10 h-64 w-64 rounded-full bg-blue-200/40 blur-3xl dark:bg-blue-500/10" />
            <div className="absolute right-0 top-0 h-80 w-80 rounded-full bg-emerald-200/35 blur-3xl dark:bg-emerald-500/10" />
            <div className="relative mx-auto max-w-3xl text-center">
              <Badge variant="secondary" className="mb-5 bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300">
                You approve everything before it goes out
              </Badge>
              <h1 className="text-5xl font-bold tracking-tight text-zinc-950 dark:text-white md:text-6xl">
                Land more interviews<br />while saving 15+ hours a week.
              </h1>
              <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-zinc-600 dark:text-zinc-400">
                Your AI assistant finds the best roles across 5 job boards, tailors your resume for each one, and submits applications automatically. You stay in complete control with two approval checkpoints.
              </p>
              <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
                <Link href="/session/new">
                  <Button size="lg" data-umami-event="cta-get-started" data-umami-event-location="hero">Start with 3 Free Applications</Button>
                </Link>
              </div>
              <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">No credit card required. Set up in under 5 minutes.</p>

              {/* Stats bar */}
              <div className="mt-10 grid gap-6 sm:grid-cols-3">
                {[
                  { value: "5 job boards", label: "Searched simultaneously" },
                  { value: "3 free credits", label: "Then from $1.20/app" },
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
            <svg className="h-4 w-4 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
            Data encrypted at rest &amp; in transit
          </span>
          <span className="flex items-center gap-2">
            <svg className="h-4 w-4 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z" /></svg>
            Payments by Stripe (PCI compliant)
          </span>
          <span className="flex items-center gap-2">
            <svg className="h-4 w-4 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" /></svg>
            Delete your data anytime
          </span>
          <span className="flex items-center gap-2">
            <svg className="h-4 w-4 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            30-day refund on unused credits
          </span>
        </div>
      </section>

      {/* Before / After comparison */}
      <section className="px-6 pb-16">
        <div className="mx-auto max-w-4xl">
          <h2 className="mb-8 text-center text-2xl font-bold">The old way vs. the JobHunter way</h2>
          <div className="grid gap-6 md:grid-cols-2">
            <Card className="rounded-3xl border-red-200/60 bg-red-50/50 dark:border-red-900/40 dark:bg-red-950/20">
              <CardContent className="p-6">
                <p className="mb-4 text-sm font-semibold text-red-700 dark:text-red-400">Manual Job Search</p>
                <ul className="space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <li className="flex items-start gap-2"><span className="mt-0.5 text-red-500">&#10005;</span>15+ hours/week copy-pasting into forms</li>
                  <li className="flex items-start gap-2"><span className="mt-0.5 text-red-500">&#10005;</span>Same generic resume sent everywhere</li>
                  <li className="flex items-start gap-2"><span className="mt-0.5 text-red-500">&#10005;</span>Skip cover letters because they take too long</li>
                  <li className="flex items-start gap-2"><span className="mt-0.5 text-red-500">&#10005;</span>Lose track of what you applied to</li>
                  <li className="flex items-start gap-2"><span className="mt-0.5 text-red-500">&#10005;</span>Burnout before you get callbacks</li>
                </ul>
              </CardContent>
            </Card>
            <Card className="rounded-3xl border-emerald-200/60 bg-emerald-50/50 dark:border-emerald-900/40 dark:bg-emerald-950/20">
              <CardContent className="p-6">
                <p className="mb-4 text-sm font-semibold text-emerald-700 dark:text-emerald-400">With JobHunter Agent</p>
                <ul className="space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <li className="flex items-start gap-2"><span className="mt-0.5 text-emerald-600">&#10003;</span>5-minute setup, AI does the rest</li>
                  <li className="flex items-start gap-2"><span className="mt-0.5 text-emerald-600">&#10003;</span>Resume tailored per role automatically</li>
                  <li className="flex items-start gap-2"><span className="mt-0.5 text-emerald-600">&#10003;</span>Custom cover letter for every application</li>
                  <li className="flex items-start gap-2"><span className="mt-0.5 text-emerald-600">&#10003;</span>Full application log with proofs</li>
                  <li className="flex items-start gap-2"><span className="mt-0.5 text-emerald-600">&#10003;</span>More interviews, less effort</li>
                </ul>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Platform Highlights */}
      <section className="px-6 pb-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-8 text-center text-2xl font-bold">Why job seekers choose JobHunter Agent</h2>
          <div className="grid gap-6 md:grid-cols-3">
            {platformHighlights.map((h) => (
              <Card key={h.title} className="rounded-3xl border-zinc-200/80 bg-white/90 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
                <CardContent className="p-6">
                  <Badge variant="secondary" className="mb-3 bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">{h.stat}</Badge>
                  <p className="text-sm font-semibold text-zinc-900 dark:text-white">{h.title}</p>
                  <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">{h.desc}</p>
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
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">Four steps from setup to submitted applications. You control every stage.</p>
          </div>
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {steps.map((step) => (
              <Card key={step.num} className="rounded-3xl border-zinc-200/80 bg-zinc-50 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
                <CardHeader>
                  <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-full bg-zinc-900 text-sm font-bold text-white dark:bg-white dark:text-zinc-900">{step.num}</div>
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

      {/* Product Screenshots / Demo */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-4 text-center text-3xl font-bold">See it in action</h2>
          <p className="mb-12 text-center text-zinc-600 dark:text-zinc-400">Real screenshots from the JobHunter Agent dashboard.</p>
          <div className="grid gap-6 md:grid-cols-3">
            {[
              {
                title: "AI Resume Coach",
                desc: "Your AI rewrites and scores your resume, then builds targeted cover letter templates.",
                gradient: "from-blue-100 to-blue-50 dark:from-blue-950/40 dark:to-blue-950/20",
                icon: (
                  <svg className="h-8 w-8 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                  </svg>
                ),
              },
              {
                title: "Live Browser Feed",
                desc: "Watch your AI agent navigate job sites and fill out applications in real time.",
                gradient: "from-emerald-100 to-emerald-50 dark:from-emerald-950/40 dark:to-emerald-950/20",
                icon: (
                  <svg className="h-8 w-8 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25A2.25 2.25 0 015.25 3h13.5A2.25 2.25 0 0121 5.25z" />
                  </svg>
                ),
              },
              {
                title: "Shortlist & Approve",
                desc: "Review AI-ranked job matches with fit scores. Approve which jobs get your application.",
                gradient: "from-violet-100 to-violet-50 dark:from-violet-950/40 dark:to-violet-950/20",
                icon: (
                  <svg className="h-8 w-8 text-violet-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z" />
                  </svg>
                ),
              },
            ].map((item) => (
              <Card key={item.title} className={`rounded-3xl border-zinc-200/80 bg-gradient-to-b ${item.gradient} shadow-sm`}>
                <CardContent className="p-6 text-center">
                  <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-white/80 shadow-sm dark:bg-zinc-900/80">
                    {item.icon}
                  </div>
                  <p className="text-sm font-semibold text-zinc-900 dark:text-white">{item.title}</p>
                  <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">{item.desc}</p>
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
              <h3 className="mb-6 text-center text-lg font-semibold">Works with all major job boards and ATS platforms</h3>
              <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-sm font-medium text-zinc-600 dark:text-zinc-400">
                {["LinkedIn", "Indeed", "Glassdoor", "ZipRecruiter", "Greenhouse", "Lever", "Workday", "Ashby", "iCIMS"].map((platform) => (
                  <span key={platform} className="rounded-lg border border-zinc-200 px-3 py-1.5 dark:border-zinc-700">{platform}</span>
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
          <p className="mb-12 text-center text-zinc-600 dark:text-zinc-400">Real results from real users.</p>
          <div className="grid gap-6 md:grid-cols-3">
            {testimonials.map((t) => (
              <Card key={t.name} className="rounded-3xl border-zinc-200/80 bg-zinc-50 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
                <CardContent className="p-6">
                  <div className="mb-3 flex items-center gap-1">
                    {[...Array(5)].map((_, i) => (
                      <svg key={i} className="h-4 w-4 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                    ))}
                  </div>
                  <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400 italic">&ldquo;{t.quote}&rdquo;</p>
                  <div className="mt-4 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-semibold text-zinc-900 dark:text-white">{t.name}</p>
                      <p className="text-xs text-zinc-500">{t.role}</p>
                    </div>
                    <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">{t.result}</Badge>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mb-10 text-center">
            <h2 className="text-3xl font-bold">Pay Per Application. No Subscriptions.</h2>
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">Start with 3 free credits. Buy packs when you&apos;re ready. Successful applications cost 1 credit, partial attempts just 0.5.</p>
          </div>

          <div className="grid gap-6 md:grid-cols-3">
            {pricingPacks.map((plan) => (
              <Card key={plan.name} className={"relative flex h-full flex-col rounded-[32px] bg-white/95 shadow-[0_18px_48px_-32px_rgba(15,23,42,0.28)] dark:bg-zinc-950 " + (plan.popular ? "border-2 border-zinc-900 dark:border-white" : "border-zinc-200 dark:border-zinc-800")}>
                {plan.popular && <div className="absolute -top-3 left-6"><Badge>Most Popular</Badge></div>}
                <CardHeader className="pb-4">
                  <CardTitle className="text-2xl">{plan.name}</CardTitle>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">{plan.summary}</p>
                  <div className="pt-2">
                    <span className="text-4xl font-bold">{plan.priceLabel}</span>
                    {plan.price > 0 && <span className="ml-2 text-sm text-zinc-500">{plan.perApp}/application</span>}
                  </div>
                  <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">{plan.apps} {plan.apps === 3 ? "free applications" : "credits"}</p>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col">
                  <ul className="mb-6 space-y-3">
                    {plan.features.map((feature) => (
                      <li key={feature} className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                        <span className="mt-0.5 text-emerald-600">&#10003;</span>
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                  <div className="mt-auto">
                    <Link href="/session/new" className="block">
                      <Button className="w-full" variant={plan.popular ? "default" : "outline"} data-umami-event="cta-select-plan" data-umami-event-plan={plan.name.toLowerCase().replace(" ", "-")}>{plan.cta}</Button>
                    </Link>
                    <p className="mt-2 text-center text-xs text-zinc-400">No credit card required</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <p className="mt-6 text-center text-sm text-zinc-500 dark:text-zinc-400">
            Also available: 100 credits for $119.99 ($1.20/credit). Need more?{" "}
            <a href="mailto:support@jobhunteragent.com" className="underline hover:text-zinc-900 dark:hover:text-white">Contact us</a> for volume pricing.
          </p>
        </div>
      </section>

      {/* Security & Compliance */}
      <section className="px-6 pb-20">
        <div className="mx-auto max-w-4xl">
          <h2 className="mb-8 text-center text-2xl font-bold">Your data is safe with us</h2>
          <div className="grid gap-6 sm:grid-cols-2 md:grid-cols-4">
            {[
              { icon: "M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z", label: "AES-256 Encryption", desc: "At rest & in transit" },
              { icon: "M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z", label: "Stripe PCI DSS", desc: "Level 1 compliant" },
              { icon: "M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0", label: "GDPR Ready", desc: "Delete data anytime" },
              { icon: "M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z", label: "30-Day Guarantee", desc: "Refund on unused credits" },
            ].map((item) => (
              <div key={item.label} className="text-center">
                <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-50 dark:bg-emerald-950/40">
                  <svg className="h-6 w-6 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d={item.icon} /></svg>
                </div>
                <p className="text-sm font-semibold text-zinc-900 dark:text-white">{item.label}</p>
                <p className="text-xs text-zinc-500">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="px-6 py-20 bg-white dark:bg-zinc-900/50">
        <div className="mx-auto max-w-3xl">
          <h2 className="mb-10 text-center text-3xl font-bold">Frequently Asked Questions</h2>
          <div className="space-y-3">
            {faqs.map((faq, i) => (
              <div key={faq.q} className="rounded-2xl border border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden">
                <button
                  className="flex w-full items-center justify-between p-5 text-left"
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                >
                  <h3 className="font-semibold text-zinc-900 dark:text-white pr-4">{faq.q}</h3>
                  <svg
                    className={`h-5 w-5 shrink-0 text-zinc-400 transition-transform ${openFaq === i ? "rotate-180" : ""}`}
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
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
              <p className="mx-auto mt-3 max-w-xl text-sm text-zinc-600 dark:text-zinc-400">Start with 3 free applications. No credit card required. See your tailored resume and matched jobs in under 5 minutes.</p>
              <div className="mt-6">
                <Link href="/session/new">
                  <Button size="lg" data-umami-event="cta-get-started" data-umami-event-location="bottom">Start Free</Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-zinc-200 px-6 py-10 dark:border-zinc-800">
        <div className="mx-auto max-w-6xl">
          <div className="flex flex-col items-center justify-between gap-6 md:flex-row">
            <div>
              <p className="text-sm font-semibold text-zinc-900 dark:text-white">JobHunter Agent</p>
              <p className="text-xs text-zinc-500">&copy; {new Date().getFullYear()} V2 Software LLC. All rights reserved.</p>
            </div>
            <div className="flex gap-6 text-sm text-zinc-500">
              <a href="#" className="hover:text-zinc-900 dark:hover:text-white">Terms of Service</a>
              <a href="#" className="hover:text-zinc-900 dark:hover:text-white">Privacy Policy</a>
              <a href="mailto:support@jobhunteragent.com" className="hover:text-zinc-900 dark:hover:text-white">Contact</a>
              <a href="https://status.jobhunteragent.com" className="hover:text-zinc-900 dark:hover:text-white" target="_blank" rel="noopener noreferrer">Status</a>
            </div>
          </div>
          {/* Social links */}
          <div className="mt-6 flex items-center justify-center gap-4">
            <a href="https://twitter.com/jobhunteragent" target="_blank" rel="noopener noreferrer" className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300" aria-label="Twitter">
              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" /></svg>
            </a>
            <a href="https://linkedin.com/company/jobhunteragent" target="_blank" rel="noopener noreferrer" className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300" aria-label="LinkedIn">
              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" /></svg>
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
