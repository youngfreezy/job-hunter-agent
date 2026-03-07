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
    summary: "Perfect for testing our approach before committing.",
    features: [
      "AI-powered job matching across top boards",
      "Professional resume optimization (1 revision)",
      "Shortlist approval before any applications",
      "Complete application tracking and downloadable materials",
    ],
    cta: "Claim Your 5 Free Applications",
    popular: false,
  },
  {
    name: "Pro",
    monthlyPrice: 49,
    weeklyPrice: 19,
    capacity: "40 applications per week",
    summary: "Ideal for active job seekers who want consistent momentum.",
    features: [
      "Unlimited resume tailoring and cover letters",
      "Live progress updates and shortlist reviews",
      "Direct communication with your AI agent",
      "Complete application history and downloads",
    ],
    cta: "Start Pro Plan",
    popular: true,
  },
  {
    name: "Power",
    monthlyPrice: 99,
    weeklyPrice: 39,
    capacity: "100 applications per week",
    summary: "Maximum coverage with hands-on control for complex applications.",
    features: [
      "Everything in Pro",
      "Real-time application monitoring",
      "Direct browser control for challenging sites",
      "Priority support for complex applications",
    ],
    cta: "Choose Power Plan",
    popular: false,
  },
];

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

const differentiators = [
  {
    title: "You control what goes out",
    body: "Guide your AI's search criteria, pause anytime, or step in when sites need verification. Every resume and job match requires your approval before submission.",
  },
  {
    title: "Only high-impact applications",
    body: "Employers only see your best work — tailored resumes and targeted matches, never generic submissions.",
  },
  {
    title: "One dashboard for everything",
    body: "Track all applications, download tailored materials, and manage follow-ups without switching tabs.",
  },
];

const heroStats = [
  {
    value: "Land more interviews",
    label: "Your AI only sends approved resumes and job matches, so every application represents you at your best.",
  },
  {
    value: "Save 15+ hours per week",
    label: "Stop copying and pasting the same application. Your AI agent handles the repetitive work.",
  },
  {
    value: "Never miss an opportunity",
    label: "Access all your tailored resumes, cover letters, and results in one dashboard. Nothing gets lost.",
  },
];

const testimonials = [
  {
    quote: "I went from spending 3 hours a day on applications to 20 minutes of review. Landed 4 interviews in my first week.",
    name: "Sarah K.",
    role: "Software Engineer",
  },
  {
    quote: "The resume optimization alone was worth it. My callback rate doubled after the AI rewrote my resume.",
    name: "Marcus T.",
    role: "Product Manager",
  },
  {
    quote: "Finally, a tool that applies to jobs without sending embarrassing generic applications. Every submission is tailored.",
    name: "Priya R.",
    role: "Data Analyst",
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
            <Link
              href="/history"
              className="text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              History
            </Link>
            <Link href="/session/new">
              <Button size="sm">Get Started</Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
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
                      You approve everything before it&apos;s sent
                    </Badge>
                  </div>
                  <h1 className="max-w-4xl text-5xl font-bold tracking-tight text-zinc-950 dark:text-white md:text-6xl">
                    Land more interviews
                    <br />
                    while saving 15+ hours a week.
                  </h1>
                  <p className="mt-6 max-w-2xl text-lg leading-8 text-zinc-600 dark:text-zinc-400">
                    Your AI assistant finds perfect roles, tailors your resume,
                    and submits applications automatically. You stay in complete
                    control with two simple approval steps.
                  </p>
                  <div className="mt-6 flex flex-wrap items-center gap-3">
                    <Link href="/session/new">
                      <Button size="lg">Get Your 5 Free Applications</Button>
                    </Link>
                    <a href="#pricing">
                      <Button size="lg" variant="outline">
                        View All Plans
                      </Button>
                    </a>
                  </div>
                  <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
                    No credit card required. Set up in under 5 minutes.
                  </p>
                  <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 dark:border-amber-800 dark:bg-amber-950/30">
                    <p className="text-sm text-amber-800 dark:text-amber-300">
                      <span className="font-semibold">Complete automation with your oversight:</span>{" "}
                      Your AI finds and applies to relevant opportunities while
                      you approve your resume and shortlist before any
                      submissions. When sites need human verification, you
                      can instantly complete them with your tailored materials.
                    </p>
                  </div>
                </div>

                <div className="mt-8 grid gap-3 sm:grid-cols-3">
                  {heroStats.map((item) => (
                    <Card
                      key={item.value}
                      className="h-full rounded-3xl border-zinc-200/80 bg-white/80 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80"
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
                      Why JobHunter Agent
                    </Badge>
                    <CardTitle className="text-2xl">
                      Automation you can trust
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4 text-sm text-zinc-300">
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <p className="mt-1 font-medium text-white">
                        Targeted, not generic
                      </p>
                      <p className="mt-1 leading-6">
                        Every application uses a resume and cover letter tailored to the specific role and company.
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <p className="mt-1 font-medium text-white">
                        Works across all major job boards
                      </p>
                      <p className="mt-1 leading-6">
                        LinkedIn, Glassdoor, ZipRecruiter, Indeed, and more. One search covers them all.
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <p className="mt-1 font-medium text-white">
                        Handles the hard parts automatically
                      </p>
                      <p className="mt-1 leading-6">
                        Standard applications submit seamlessly. For complex sites, your customized materials are ready so you finish in one click.
                      </p>
                    </div>
                  </CardContent>
                </Card>
                <div className="grid gap-4 sm:grid-cols-3">
                  {differentiators.map((item) => (
                    <Card
                      key={item.title}
                      className="h-full rounded-3xl border-zinc-200/80 bg-white/90 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80"
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

      {/* Social Proof Section */}
      <section className="px-6 pb-10">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-8 text-center text-2xl font-bold">
            Job seekers are landing interviews faster
          </h2>
          <div className="grid gap-6 md:grid-cols-3">
            {testimonials.map((t) => (
              <Card
                key={t.name}
                className="rounded-3xl border-zinc-200/80 bg-white/90 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
              >
                <CardContent className="p-6">
                  <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400">
                    &ldquo;{t.quote}&rdquo;
                  </p>
                  <div className="mt-4">
                    <p className="text-sm font-semibold text-zinc-900 dark:text-white">
                      {t.name}
                    </p>
                    <p className="text-xs text-zinc-500">{t.role}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Application Command Center CTA */}
      <section className="px-6 pb-10">
        <div className="mx-auto max-w-6xl">
          <Card className="rounded-[28px] border-emerald-200 bg-gradient-to-r from-emerald-50 to-blue-50 shadow-sm dark:border-emerald-900 dark:from-emerald-950/30 dark:to-blue-950/30">
            <CardContent className="flex flex-col gap-4 py-8 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h3 className="text-xl font-semibold">
                  Your application command center
                </h3>
                <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
                  Monitor every application in one organized dashboard.
                  Download customized resumes and cover letters, complete
                  applications needing human input, and track your progress
                  toward landing more interviews.
                </p>
              </div>
              <Link href="/session/new">
                <Button size="lg" className="whitespace-nowrap">
                  Get Your 5 Free Applications
                </Button>
              </Link>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* How It Works */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mb-12 flex items-end justify-between gap-6">
            <div>
              <h2 className="text-3xl font-bold">How It Works</h2>
              <p className="mt-2 max-w-2xl text-zinc-600 dark:text-zinc-400">
                Four steps from setup to submitted applications. You control every stage.
              </p>
            </div>
            <div className="hidden rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-600 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400 md:block">
              Two approval stops. Full transparency. Zero surprises.
            </div>
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
                  <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400">
                    {step.desc}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mb-10 flex flex-col items-start justify-between gap-6 lg:flex-row lg:items-end">
            <div>
              <h2 className="text-3xl font-bold">
                Start Free, Scale When Ready
              </h2>
              <p className="mt-2 max-w-2xl text-zinc-600 dark:text-zinc-400">
                Experience the full platform with 5 free applications. Upgrade when you&apos;re ready to accelerate results.
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
                  Professional job search support
                </h3>
                <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
                  For personalized strategy, custom outreach, or fully managed services, our expert team provides dedicated support beyond the platform.
                </p>
              </div>
              <Button variant="outline">Schedule Your Strategy Call</Button>
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
