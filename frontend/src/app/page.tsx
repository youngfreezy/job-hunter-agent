"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const plans = [
  {
    name: "Starter",
    price: 49,
    period: "week",
    apps: 25,
    features: ["Status Feed (live text updates)", "25 applications/week", "Resume coaching & scoring", "Cover letter generation", "Email support"],
    cta: "Start Free Trial",
    popular: false,
  },
  {
    name: "Professional",
    price: 99,
    period: "week",
    apps: 75,
    features: ["Screenshot Feed + Chat steering", "75 applications/week", "Resume coaching & scoring", "Cover letter generation", "LinkedIn profile advice", "Priority support"],
    cta: "Start Free Trial",
    popular: true,
  },
  {
    name: "Executive",
    price: 199,
    period: "week",
    apps: 200,
    features: ["Live browser takeover (on-demand)", "200 applications/week", "Resume coaching & scoring", "Cover letter generation", "LinkedIn profile advice", "Direct browser control", "Dedicated support"],
    cta: "Start Free Trial",
    popular: false,
  },
];

const steps = [
  { num: "1", title: "Upload & Configure", desc: "Upload your resume, enter your target keywords, locations, and preferences." },
  { num: "2", title: "AI Career Coach", desc: "Our AI rewrites your resume as a personal salesperson, scores it, and builds cover letter templates." },
  { num: "3", title: "Discover & Score", desc: "Agents scan Indeed, LinkedIn, Glassdoor, ZipRecruiter, and Google Jobs simultaneously." },
  { num: "4", title: "Review & Approve", desc: "Review the shortlist with fit scores. Approve which jobs to apply to." },
  { num: "5", title: "Watch & Steer", desc: "Watch the agent apply in real-time. Chat to steer it, or take direct browser control." },
  { num: "6", title: "Get Results", desc: "Receive a detailed report with submission proofs, metrics, and next steps." },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      {/* Nav */}
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4 flex items-center justify-between max-w-7xl mx-auto">
        <span className="text-xl font-bold tracking-tight">JobHunter Agent</span>
        <div className="flex items-center gap-4">
          <Link href="/dashboard" className="text-sm text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white">
            Dashboard
          </Link>
          <Link href="/session/new">
            <Button size="sm">Get Started</Button>
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="px-6 py-24 text-center max-w-4xl mx-auto">
        <Badge variant="secondary" className="mb-4">US Only</Badge>
        <h1 className="text-5xl font-bold tracking-tight mb-6">
          Stop applying to jobs.<br />Let AI do it for you.
        </h1>
        <p className="text-xl text-zinc-600 dark:text-zinc-400 mb-8 max-w-2xl mx-auto">
          JobHunter Agent scans 5 major job boards, tailors your resume per job,
          generates cover letters, and submits applications — while you watch and steer in real-time.
        </p>
        <div className="flex gap-4 justify-center">
          <Link href="/session/new">
            <Button size="lg">Start Your First Session</Button>
          </Link>
          <a href="#pricing">
            <Button size="lg" variant="outline">View Pricing</Button>
          </a>
        </div>
      </section>

      {/* How it works */}
      <section className="px-6 py-20 bg-zinc-50 dark:bg-zinc-900">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12">How It Works</h2>
          <div className="grid md:grid-cols-3 gap-6">
            {steps.map((step) => (
              <Card key={step.num} className="relative">
                <CardHeader>
                  <div className="w-8 h-8 rounded-full bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 flex items-center justify-center text-sm font-bold mb-2">
                    {step.num}
                  </div>
                  <CardTitle className="text-lg">{step.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">{step.desc}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="px-6 py-20 max-w-6xl mx-auto">
        <h2 className="text-3xl font-bold text-center mb-4">Simple Weekly Pricing</h2>
        <p className="text-center text-zinc-600 dark:text-zinc-400 mb-12">
          Cancel anytime. No long-term commitment.
        </p>
        <div className="grid md:grid-cols-3 gap-6">
          {plans.map((plan) => (
            <Card key={plan.name} className={plan.popular ? "border-zinc-900 dark:border-white border-2 relative" : ""}>
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <Badge>Most Popular</Badge>
                </div>
              )}
              <CardHeader className="text-center">
                <CardTitle className="text-xl">{plan.name}</CardTitle>
                <div className="mt-4">
                  <span className="text-4xl font-bold">${plan.price}</span>
                  <span className="text-zinc-500">/{plan.period}</span>
                </div>
                <p className="text-sm text-zinc-500 mt-1">{plan.apps} applications/week</p>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 mb-6">
                  {plan.features.map((f) => (
                    <li key={f} className="text-sm flex items-start gap-2">
                      <span className="text-green-600 mt-0.5">✓</span>
                      {f}
                    </li>
                  ))}
                </ul>
                <Link href="/session/new" className="block">
                  <Button className="w-full" variant={plan.popular ? "default" : "outline"}>
                    {plan.cta}
                  </Button>
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-zinc-200 dark:border-zinc-800 px-6 py-8">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-sm text-zinc-500">
            © {new Date().getFullYear()} V2 Software LLC. All rights reserved.
          </p>
          <div className="flex gap-6 text-sm text-zinc-500">
            <a href="#" className="hover:text-zinc-900 dark:hover:text-white">Terms</a>
            <a href="#" className="hover:text-zinc-900 dark:hover:text-white">Privacy</a>
            <a href="#" className="hover:text-zinc-900 dark:hover:text-white">Contact</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
